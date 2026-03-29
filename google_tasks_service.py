import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import logging
from google_oauth_config import resolve_google_oauth_client_config

logger = logging.getLogger(__name__)

class GoogleTasksService:
    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build('tasks', 'v1', credentials=credentials, cache_discovery=False)

    @classmethod
    def from_user_token(cls, token_data: dict):
        """Create GoogleTasksService from user token data"""
        client_id, client_secret = resolve_google_oauth_client_config()
        credentials = Credentials(
            token=token_data.get('access_token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )
        if credentials.expired and credentials.refresh_token:
            try:
                from google.auth.transport.requests import Request
                credentials.refresh(Request())
                logger.info("Refreshed expired Tasks token")
            except Exception as e:
                logger.error(f"Failed to refresh Tasks token: {e}")
        return cls(credentials)

    def get_task_lists(self) -> List[Dict[str, Any]]:
        """
        Get all task lists

        Returns:
            List of task lists
        """
        try:
            results = self.service.tasklists().list().execute()
            return results.get('items', [])
        except Exception as e:
            logger.error(f"Error getting task lists: {e}")
            return []

    def get_or_create_task_list(self, title: str = "Inbotic") -> Optional[Dict[str, Any]]:
        """
        Get existing task list or create new one

        Args:
            title: Title for the task list

        Returns:
            Task list dictionary or None if error
        """
        try:
            # Check if task list already exists
            task_lists = self.get_task_lists()
            for task_list in task_lists:
                if task_list['title'] == title:
                    return task_list

            # Create new task list
            new_list = self.service.tasklists().insert(
                body={'title': title}
            ).execute()

            logger.info(f"Created new task list: {title}")
            return new_list

        except Exception as e:
            logger.error(f"Error getting/creating task list: {e}")
            return None

    def create_task(self, task_list_id: str, title: str, notes: str = None,
                   due_date: str = None, priority: str = None, default_due_time_utc: str = "09:00:00.000Z") -> Optional[Dict[str, Any]]:
        """
        Create a new task

        Args:
            task_list_id: ID of the task list
            title: Task title
            notes: Task notes/description
            due_date: Due date in YYYY-MM-DD format
            priority: Task priority (high, medium, low)

        Returns:
            Created task dictionary or None if error
        """
        try:
            task_body = {
                'title': title,
                'notes': notes or ''
            }

            if due_date:
                # If caller passes a full datetime (contains 'T'), use as-is. Otherwise add a default time.
                task_body['due'] = due_date if 'T' in due_date else f"{due_date}T{default_due_time_utc}"

            # Create the task
            task = self.service.tasks().insert(
                tasklist=task_list_id,
                body=task_body
            ).execute()

            logger.info(f"Created task: {title}")
            return task

        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return None

    def create_tasks_from_email(self,
                              task_list_id: str,
                              email_data: Dict[str, Any],
                              extract_deadlines: bool = True,
                              max_days_ahead: int = 60,
                              default_due_time_utc: str = "09:00:00.000Z",
                              create_action_tasks: bool = False,
                              pre_reminder_days: int = 1,
                              pre_reminder_hours: int = 0,
                              create_pre_reminder: bool = True,
                              dedupe: bool = True) -> List[Dict[str, Any]]:
        """
        Create tasks from email data

        Args:
            task_list_id: ID of the task list
            email_data: Email data dictionary
            extract_deadlines: Whether to extract deadlines from email
            pre_reminder_hours: Create a reminder N hours before deadline (e.g., 1 for 1-hour prior)

        Returns:
            List of created tasks
        """
        created_tasks = []

        try:
            # Extract deadlines first
            deadline_info = None
            if extract_deadlines:
                # Debug: Log what we're processing
                logger.info(f"Extracting deadline from email - Subject: {email_data.get('subject', 'N/A')[:50]}")
                logger.info(f"Email body snippet: {email_data.get('body', 'N/A')[:100]}...")
                deadline_info = self._extract_deadline_info(email_data)

            # If no deadline found, or deadline is in the past, do not create tasks
            if not deadline_info:
                logger.info("No deadline found in email; skipping task creation")
                return created_tasks

            due_date = deadline_info['due_date']
            due_time_raw = deadline_info.get('due_time') or default_due_time_utc

            def _normalize_time_hms(time_value: str, fallback: str = "09:00:00") -> str:
                """Normalize time values like HH:MM, HH:MM:SS, HH:MM:SS.000Z to HH:MM:SS."""
                if not time_value:
                    return fallback
                text = str(time_value).strip()
                if 'T' in text:
                    text = text.split('T', 1)[1]
                text = text.replace('Z', '')
                text = text.split('.', 1)[0]
                # Remove timezone offsets if present.
                text = re.sub(r'([+-]\d{2}:?\d{2})$', '', text).strip()
                parts = text.split(':')
                if len(parts) == 2:
                    text = f"{parts[0]}:{parts[1]}:00"
                m = re.fullmatch(r'([01]?\d|2[0-3]):([0-5]\d):([0-5]\d)', text)
                if not m:
                    return fallback
                return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}:{int(m.group(3)):02d}"

            due_time_hms = _normalize_time_hms(due_time_raw, "09:00:00")
            due_time_utc = f"{due_time_hms}.000Z"

            # Ensure deadline is today or future
            try:
                from datetime import datetime as _dt
                email_due = _dt.strptime(due_date, "%Y-%m-%d").date()
                today = _dt.now().date()
                if email_due < today:
                    logger.info(f"Deadline {due_date} is in the past; skipping task creation")
                    return created_tasks
                # Guard: only create if within max_days_ahead window
                if (email_due - today).days > max_days_ahead:
                    logger.info(f"Deadline {due_date} is beyond {max_days_ahead} days; skipping task creation")
                    return created_tasks
            except Exception:
                # If parsing fails unexpectedly, be safe and skip
                logger.info("Unable to parse due date; skipping task creation")
                return created_tasks

            # Keep marker for traceability in notes; dedupe is title-based.
            email_id = email_data.get('id') or email_data.get('gmail_message_id')
            marker = f"[IA:{email_id}]" if email_id else None

            # Create concise task title/notes focused on what the task is about.
            import re as _re
            import html as _html

            def _clean_text(raw: str) -> str:
                if not raw:
                    return ""
                text = _html.unescape(raw)
                text = _re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', text, flags=_re.IGNORECASE | _re.DOTALL)
                text = _re.sub(r'<[^>]+>', ' ', text)
                text = _re.sub(r'\s+', ' ', text).strip()
                return text

            def _short_summary(raw: str, max_len: int = 180) -> str:
                cleaned = _clean_text(raw)
                if not cleaned:
                    return ""
                sentence = _re.split(r'(?<=[.!?])\s+', cleaned)[0].strip()
                if len(sentence) >= 20:
                    cleaned = sentence
                return cleaned[:max_len].rstrip()

            raw_subject = (email_data.get('subject') or 'Task').strip()
            clean_subject = _clean_text(raw_subject)
            clean_subject = _re.sub(r'^(?:re|fw|fwd)\s*:\s*', '', clean_subject, flags=_re.IGNORECASE).strip()
            main_task_title = clean_subject[:90] if clean_subject else 'Task from email'
            if len(clean_subject) > 90:
                main_task_title += '...'

            def _normalize_title(text: str) -> str:
                return _re.sub(r'\s+', ' ', (text or '').strip()).lower()

            existing_title_keys = set()
            if dedupe:
                try:
                    existing_tasks = self.get_tasks(
                        task_list_id=task_list_id,
                        max_results=300,
                        show_completed=True,
                        show_hidden=False,
                    )
                    existing_title_keys = {
                        _normalize_title(t.get('title', ''))
                        for t in existing_tasks
                        if t.get('title')
                    }
                except Exception:
                    # If fetching tasks fails, proceed without dedupe.
                    existing_title_keys = set()

            if dedupe and _normalize_title(main_task_title) in existing_title_keys:
                logger.info("Task with same title already exists; skipping create")
                return [{"dedupe": True, "message": "Task with same title already exists"}]

            thread_id = email_data.get('thread_id') or email_data.get('id')
            gmail_link = f"https://mail.google.com/mail/u/0/#all/{thread_id}" if thread_id else None

            about = _short_summary(email_data.get('body') or '')
            if not about:
                about = clean_subject

            lines = [f"About: {about}"]
            if email_data.get('sender'):
                lines.append(f"From: {email_data['sender']}")
            # Add the extracted time prominently
            if due_time_hms:
                lines.append(f"⏰ Time: {due_time_hms[:5]} UTC")  # Show HH:MM format
            if gmail_link:
                lines.append(f"Link: {gmail_link}")
            if marker:
                lines.append(marker)
            main_notes = "\n".join(lines)

            main_task = self.create_task(
                task_list_id=task_list_id,
                title=main_task_title,
                notes=main_notes,
                due_date=due_date,
                default_due_time_utc=due_time_utc
            )
            if main_task:
                created_tasks.append(main_task)
                if dedupe:
                    existing_title_keys.add(_normalize_title(main_task_title))

            # Optionally create a pre-deadline reminder task (clean, simple reminder)
            if create_pre_reminder:
                try:
                    from datetime import datetime as _dt, timedelta as _td
                    
                    # Support both day-based and hour-based pre-reminders
                    if pre_reminder_hours > 0 and due_time_hms:
                        # Hour-based reminder: subtract N hours from the deadline time
                        try:
                            # Parse the deadline: due_date (YYYY-MM-DD) and due_time (HH:MM:SS)
                            deadline_dt = _dt.strptime(f"{due_date} {due_time_hms}", "%Y-%m-%d %H:%M:%S")
                            reminder_dt = deadline_dt - _td(hours=pre_reminder_hours)
                            pre_due_date = reminder_dt.strftime('%Y-%m-%d')
                            pre_due_time = reminder_dt.strftime('%H:%M:%S')
                            
                            # Only create if still in the future
                            if reminder_dt > _dt.now():
                                reminder_title = f"⏰ {pre_reminder_hours}h reminder: {email_data['subject'][:50]}" + ("..." if len(email_data['subject']) > 50 else "")
                                if (not dedupe) or (_normalize_title(reminder_title) not in existing_title_keys):
                                    reminder = self.create_task(
                                        task_list_id=task_list_id,
                                        title=reminder_title,
                                        notes=(f"Due in {pre_reminder_hours} hour(s) →  {due_date} {due_time_hms}\nFrom: {email_data['sender']}" + (f"\nLink: {gmail_link}" if gmail_link else "") + (f"\n{marker}" if marker else "")),
                                        due_date=pre_due_date,
                                        default_due_time_utc=f"{pre_due_time}.000Z"
                                    )
                                    if reminder:
                                        created_tasks.append(reminder)
                                        if dedupe:
                                            existing_title_keys.add(_normalize_title(reminder_title))
                        except Exception as e:
                            logger.debug(f"Failed to create hour-based reminder: {e}")
                    
                    elif pre_reminder_days > 0:
                        # Day-based reminder: subtract N days from the deadline
                        pre_due = (email_due - _td(days=pre_reminder_days)).strftime('%Y-%m-%d')
                        # Only if still in the future (or today)
                        if _dt.strptime(pre_due, '%Y-%m-%d').date() >= _dt.now().date():
                            reminder_title = f"Reminder: {email_data['subject'][:60]}" + ("..." if len(email_data['subject']) > 60 else "")
                            if (not dedupe) or (_normalize_title(reminder_title) not in existing_title_keys):
                                reminder = self.create_task(
                                    task_list_id=task_list_id,
                                    title=reminder_title,
                                    notes=(f"Due soon → {due_date} {due_time_hms}" + f"\nFrom: {email_data['sender']}" + (f"\nLink: {gmail_link}" if gmail_link else "") + (f"\n{marker}" if marker else "")),
                                    due_date=pre_due,
                                    default_due_time_utc=due_time_utc
                                )
                                if reminder:
                                    created_tasks.append(reminder)
                                    if dedupe:
                                        existing_title_keys.add(_normalize_title(reminder_title))
                except Exception as _:
                    pass

            # Optionally create action tasks with same due date
            if create_action_tasks:
                action_tasks = self._extract_action_tasks(email_data)
                for action_task in action_tasks:
                    action_title = action_task.get('title', '')
                    if dedupe and _normalize_title(action_title) in existing_title_keys:
                        continue
                    task = self.create_task(
                        task_list_id=task_list_id,
                        title=action_title,
                        notes=action_task['notes'],
                        due_date=due_date,
                        default_due_time_utc=due_time_utc
                    )
                    if task:
                        created_tasks.append(task)
                        if dedupe:
                            existing_title_keys.add(_normalize_title(action_title))

            logger.info(f"Created {len(created_tasks)} deadline-based tasks from email")
            return created_tasks

        except Exception as e:
            logger.error(f"Error creating tasks from email: {e}")
            return created_tasks

    def _extract_deadline_info(self, email_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract deadline information from email using a staged deterministic parser:
        1) keyword-adjacent windows, 2) subject-focused scan, 3) full-text fallback.
        Also extracts time if present in the deadline text, and searches for times separately.

        Args:
            email_data: Email data dictionary containing 'subject' and 'body' keys

        Returns:
            Dictionary with 'due_date' (YYYY-MM-DD), 'due_time' (HH:MM:SS format if found),
            and 'description' of the deadline, or None if no valid deadline found
        """
        import re
        from datetime import datetime, timedelta
        from dateutil.parser import parse as parse_date

        # Time pattern that can extract time from anywhere in the email
        # Time pattern that can extract time from anywhere in the email
        # Time pattern that can extract time from anywhere in the email
        TIME_EXTRACTION_PATTERN = re.compile(
            r'\b(\d{1,2})\s*(?::(\d{2}))?\s*(am|pm)\b|'
            r'\b([01]\d|2[0-3]):([0-5]\d)\s*(?:utc|gmt|ist)?\b',
            re.IGNORECASE
        )

        ABSOLUTE_PATTERNS = [
            re.compile(r'\b20\d{2}[\-\/.](?:0?[1-9]|1[0-2])[\-\/.](?:0?[1-9]|[12]\d|3[01])\b', re.IGNORECASE),
            re.compile(r'\b(?:0?[1-9]|[12]\d|3[01])[\-\/.](?:0?[1-9]|1[0-2])[\-\/.](?:\d{2}|\d{4})\b', re.IGNORECASE),
            re.compile(r'\b(?:0?[1-9]|1[0-2])[\-\/.](?:0?[1-9]|[12]\d|3[01])[\-\/.](?:\d{2}|\d{4})\b', re.IGNORECASE),
            re.compile(r'\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[\s,]+\d{1,2}(?:st|nd|rd|th)?(?:[\s,]+\d{4})?(?:\s+(\d{1,2}):(\d{2})(?:\s*(?:am|pm))?)?(?:\s*\(?(?:utc|gmt|ist)\)?)?\b', re.IGNORECASE),
            re.compile(r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:,?\s*\d{4})?(?:\s+(\d{1,2}):(\d{2})(?:\s*(?:am|pm))?)?(?:\s*\(?(?:utc|gmt|ist)\)?)?\b', re.IGNORECASE),
            re.compile(r'\b(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?),?\s+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)[\s,]+\d{1,2}(?:st|nd|rd|th)?(?:[\s,]+\d{4})?(?:\s+(\d{1,2}):(\d{2})(?:\s*(?:am|pm))?)?(?:\s*\(?(?:utc|gmt|ist)\)?)?\b', re.IGNORECASE),
        ]

        RELATIVE_PATTERN = re.compile(
            r'\b('
            r'day\s+after\s+tomorrow|tomorrow|tommorow|today|tonight|eod|end\s+of\s+day|'
            r'next\s+week|next\s+month|'
            r'next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|'
            r'this\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|'
            r'in\s+\d{1,2}\s+(?:day|days|week|weeks|month|months)'
            r')\b',
            re.IGNORECASE,
        )

        KEYWORD_PATTERN = re.compile(
            r'\b('
            r'deadline|due(?:\s+date)?|apply\s+by|submit(?:ted)?\s+by|'
            r'register\s+by|registration\s+closes?|closing\s+date|'
            r'last\s+date|before|until|no\s+later\s+than|not\s+after|'
            r'starts?\s+on|begins?\s+on|scheduled\s+for|held\s+on|takes\s+place\s+on|'
            r'expires?|ends?|assessment|exam|test|quiz|assignment|project|submission|deadline|'
            r'meeting|event|class|workshop|seminar|conference|webinar|interview|presentation|call|demo|launch|release|go\s+live|'
            r')\b',
            re.IGNORECASE,
        )

        def _has_explicit_year(text: str) -> bool:
            return bool(re.search(r'\b(?:19|20)\d{2}\b', text))

        def _normalize_yearless(candidate_date):
            if candidate_date < base_date.date() - timedelta(days=1):
                try:
                    return candidate_date.replace(year=candidate_date.year + 1)
                except ValueError:
                    return candidate_date + timedelta(days=365)
            return candidate_date

        def parse_relative_date(date_str: str):
            text = re.sub(r'\s+', ' ', date_str.lower()).strip()
            if text in ('today', 'tonight', 'eod', 'end of day'):
                return base_date.date()
            if text in ('tomorrow', 'tommorow'):
                return (base_date + timedelta(days=1)).date()
            if text == 'day after tomorrow':
                return (base_date + timedelta(days=2)).date()
            if text == 'next week':
                return (base_date + timedelta(weeks=1)).date()
            if text == 'next month':
                return (base_date + timedelta(days=30)).date()

            in_delta = re.search(r'in\s+(\d{1,2})\s+(day|days|week|weeks|month|months)', text, re.IGNORECASE)
            if in_delta:
                amount = int(in_delta.group(1))
                unit = in_delta.group(2).lower()
                if 'day' in unit:
                    return (base_date + timedelta(days=amount)).date()
                if 'week' in unit:
                    return (base_date + timedelta(weeks=amount)).date()
                return (base_date + timedelta(days=amount * 30)).date()

            weekday_map = {
                'monday': 0,
                'tuesday': 1,
                'wednesday': 2,
                'thursday': 3,
                'friday': 4,
                'saturday': 5,
                'sunday': 6,
            }
            wmatch = re.search(r'\b(this|next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', text)
            if wmatch:
                mode, weekday_name = wmatch.group(1).lower(), wmatch.group(2).lower()
                target = weekday_map[weekday_name]
                now_wd = base_date.weekday()
                delta = (target - now_wd) % 7
                if mode == 'next':
                    delta = delta + 7 if delta == 0 else delta
                return (base_date + timedelta(days=delta)).date()

            return None

        def parse_absolute_date(date_str: str):
            cleaned = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', date_str.strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r',', ' ', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()

            # Extract time if present (HH:MM with optional AM/PM)
            time_match = re.search(r'(\d{1,2}):(\d{2})(?:\s*(?:am|pm))?', cleaned, re.IGNORECASE)
            extracted_time = None
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                # Check for AM/PM
                am_pm_match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)', cleaned, re.IGNORECASE)
                if am_pm_match:
                    am_pm = am_pm_match.group(3).lower()
                    if am_pm == 'pm' and hour != 12:
                        hour += 12
                    elif am_pm == 'am' and hour == 12:
                        hour = 0
                extracted_time = f"{hour:02d}:{minute:02d}:00.000Z"

            numeric = re.fullmatch(r'(\d{1,4})[\-\/.](\d{1,2})[\-\/.](\d{1,4})', cleaned)
            if numeric:
                a, b, c = [int(x) for x in numeric.groups()]
                year = month = day = None
                if a >= 1000:
                    year, month, day = a, b, c
                else:
                    year = c + 2000 if c < 100 else c
                    if a > 12:
                        day, month = a, b
                    elif b > 12:
                        month, day = a, b
                    else:
                        day, month = a, b
                try:
                    return (datetime(year, month, day).date(), extracted_time)
                except ValueError:
                    return (None, None)

            try:
                parsed = parse_date(cleaned, dayfirst=True, fuzzy=True, default=base_date)
            except Exception:
                return (None, None)

            if not parsed:
                return (None, None)

            candidate = parsed.date()
            if not _has_explicit_year(cleaned):
                candidate = _normalize_yearless(candidate)
            return (candidate, extracted_time)

        def collect_candidates(text: str, stage: str, base_score: int):
            candidates = []
            for pattern in ABSOLUTE_PATTERNS:
                for match in pattern.finditer(text):
                    raw = match.group(0).strip()
                    parsed_date, parsed_time = parse_absolute_date(raw)
                    if parsed_date:
                        candidates.append({'date': parsed_date, 'time': parsed_time, 'raw': raw, 'stage': stage, 'score': base_score})
            for match in RELATIVE_PATTERN.finditer(text):
                raw = match.group(0).strip()
                parsed = parse_relative_date(raw)
                if parsed:
                    candidates.append({'date': parsed, 'time': None, 'raw': raw, 'stage': stage, 'score': base_score + 5})
            return candidates

        # Get email content
        subject = email_data.get('subject', '')
        body = email_data.get('body', '')
        email_date = email_data.get('date')

        # Use email timestamp as parsing anchor when available.
        base_date = datetime.now()
        if email_date:
            try:
                parsed_email_dt = parse_date(email_date)
                if parsed_email_dt:
                    base_date = parsed_email_dt
            except Exception:
                pass


        subject_text = re.sub(r'\s+', ' ', subject).strip()
        combined_text = re.sub(r'\s+', ' ', f"{subject} {body}").strip()

        candidates = []

        # Stage 1: high-confidence windows around deadline keywords.
        for km in KEYWORD_PATTERN.finditer(combined_text):
            start = max(0, km.start() - 25)
            end = min(len(combined_text), km.end() + 110)
            window = combined_text[start:end]
            candidates.extend(collect_candidates(window, 'keyword-window', 100))

        # Stage 2: subject-only scan.
        if subject_text:
            candidates.extend(collect_candidates(subject_text, 'subject', 85))

        # Stage 3: full-text fallback.
        candidates.extend(collect_candidates(combined_text, 'full-text', 60))

        if not candidates:
            return None

        today = datetime.now().date()
        filtered = []
        seen = set()
        for item in candidates:
            date_val = item['date']
            if date_val < (today - timedelta(days=1)):
                continue
            if date_val > (today + timedelta(days=730)):
                continue
            key = (item['raw'].lower(), date_val.isoformat(), item['stage'])
            if key in seen:
                continue
            seen.add(key)
            filtered.append(item)

        if not filtered:
            return None

        filtered.sort(key=lambda x: (-x['score'], x['date']))
        winner = filtered[0]
        description = f"Detected from {winner['stage']}: {winner['raw']}"
        extracted_time = winner.get('time')
        
        logger.info(
            f"Found deadline: {winner['date']} from '{winner['raw']}' "
            f"(stage={winner['stage']}, score={winner['score']}, time={extracted_time or 'N/A'})"
        )

        # If we have a date but no time, search the entire email for any time mention
        if not extracted_time:
            full_text = f"{subject} {body}".lower()
            time_match = TIME_EXTRACTION_PATTERN.search(full_text)
            if time_match:
                if time_match.group(1):  # First pattern: H or HH with optional :MM and am/pm
                    try:
                        hour = int(time_match.group(1))
                        minute = int(time_match.group(2)) if time_match.group(2) else 0
                        am_pm = time_match.group(3).lower() if time_match.group(3) else None
                        
                        if am_pm:
                            if am_pm == 'pm' and hour != 12:
                                hour += 12
                            elif am_pm == 'am' and hour == 12:
                                hour = 0
                        
                        extracted_time = f"{hour:02d}:{minute:02d}:00.000Z"
                    except (ValueError, TypeError):
                        pass
                elif time_match.group(4):  # Second pattern: 24-hour format HH:MM
                    try:
                        hour = int(time_match.group(4))
                        minute = int(time_match.group(5)) if time_match.group(5) else 0
                        extracted_time = f"{hour:02d}:{minute:02d}:00.000Z"
                    except (ValueError, TypeError):
                        pass
                
                if extracted_time:
                    logger.info(f"Extracted time from email body: {extracted_time}")

        return {
            'due_date': winner['date'].strftime('%Y-%m-%d'),
            'due_time': extracted_time,
            'description': description[:200]
        }

    def get_tasks(self, task_list_id: str, max_results: int = 100, show_completed: bool = True, show_hidden: bool = False) -> List[Dict[str, Any]]:
        """
        Get tasks from a list

        Args:
            task_list_id: ID of the task list
            max_results: Maximum number of tasks to retrieve
            show_completed: Whether to include completed tasks
            show_hidden: Whether to include hidden tasks

        Returns:
            List of tasks
        """
        try:
            results = self.service.tasks().list(
                tasklist=task_list_id,
                maxResults=max_results,
                showCompleted=show_completed,
                showHidden=show_hidden
            ).execute()

            return results.get('items', [])
        except Exception as e:
            logger.error(f"Error getting tasks: {e}")
            return []

    def complete_task(self, task_list_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Mark a task as completed.
        """
        return self.update_task(task_list_id, task_id, {'status': 'completed'})

    def update_task(self, task_list_id: str, task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update a task
        
        Args:
            task_list_id: ID of the task list
            task_id: ID of the task
            updates: Dictionary of updates to apply

        Returns:
            Updated task dictionary or None if error
        """
        try:
            updated_task = self.service.tasks().patch(
                tasklist=task_list_id,
                task=task_id,
                body=updates
            ).execute()

            logger.info(f"Updated task {task_id}")
            return updated_task

        except Exception as e:
            logger.error(f"Error updating task: {e}")
            return None

    def delete_task(self, task_list_id: str, task_id: str) -> bool:
        """
        Delete a task

        Args:
            task_list_id: ID of the task list
            task_id: ID of the task

        Returns:
            True if successful
        """
        try:
            self.service.tasks().delete(
                tasklist=task_list_id,
                task=task_id
            ).execute()

            logger.info(f"Deleted task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            return False
