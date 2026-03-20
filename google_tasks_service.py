import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import logging

logger = logging.getLogger(__name__)

class GoogleTasksService:
    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build('tasks', 'v1', credentials=credentials, cache_discovery=False)

    @classmethod
    def from_user_token(cls, token_data: dict):
        """Create GoogleTasksService from user token data"""
        credentials = Credentials(
            token=token_data.get('access_token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("CLIENT_ID"),
            client_secret=os.getenv("CLIENT_SECRET")
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
                              create_pre_reminder: bool = True,
                              dedupe: bool = True) -> List[Dict[str, Any]]:
        """
        Create tasks from email data

        Args:
            task_list_id: ID of the task list
            email_data: Email data dictionary
            extract_deadlines: Whether to extract deadlines from email

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

            # Optionally dedupe by email id marker
            email_id = email_data.get('id') or email_data.get('gmail_message_id')
            marker = f"[IA:{email_id}]" if email_id else None

            if dedupe and marker:
                try:
                    existing_tasks = self.get_tasks(task_list_id, max_results=100)
                    for t in existing_tasks:
                        notes = t.get('notes', '') or ''
                        title = t.get('title', '') or ''
                        if marker in notes or marker in title:
                            logger.info("Task(s) for this email already exist; skipping due to dedupe marker")
                            # Return a marker to indicate dedupe, not failure
                            return [{"dedupe": True, "message": "Task already exists"}]
                except Exception:
                    # If fetching tasks fails, proceed without dedupe
                    pass

            # Create main task for the email
            main_task_title = f"Process: {email_data['subject'][:50]}"
            if len(email_data['subject']) > 50:
                main_task_title += "..."

            # Build clean notes with context and Gmail link
            thread_id = email_data.get('thread_id')
            gmail_link = f"https://mail.google.com/mail/u/0/#all/{thread_id}" if thread_id else None
            lines = []
            lines.append(f"From: {email_data['sender']}")
            if gmail_link:
                lines.append(f"Link: {gmail_link}")
            if marker:
                lines.append(marker)
            # Add a short preview of body
            preview = (email_data['body'] or '')[:500]
            if preview:
                lines.append("")
                lines.append(preview + ("..." if len(email_data['body']) > 500 else ""))
            main_notes = "\n".join(lines)

            main_task = self.create_task(
                task_list_id=task_list_id,
                title=main_task_title,
                notes=main_notes,
                due_date=due_date,
                default_due_time_utc=default_due_time_utc
            )
            if main_task:
                created_tasks.append(main_task)

            # Optionally create a pre-deadline reminder task (clean, simple reminder)
            if create_pre_reminder and pre_reminder_days > 0:
                try:
                    from datetime import datetime as _dt, timedelta as _td
                    pre_due = (email_due - _td(days=pre_reminder_days)).strftime('%Y-%m-%d')
                    # Only if still in the future (or today)
                    if _dt.strptime(pre_due, '%Y-%m-%d').date() >= _dt.now().date():
                        reminder_title = f"Reminder: {email_data['subject'][:60]}" + ("..." if len(email_data['subject']) > 60 else "")
                        reminder = self.create_task(
                            task_list_id=task_list_id,
                            title=reminder_title,
                            notes=(f"Due soon → {due_date}\nFrom: {email_data['sender']}" + (f"\nLink: {gmail_link}" if gmail_link else "") + (f"\n{marker}" if marker else "")),
                            due_date=pre_due,
                            default_due_time_utc=default_due_time_utc
                        )
                        if reminder:
                            created_tasks.append(reminder)
                except Exception as _:
                    pass

            # Optionally create action tasks with same due date
            if create_action_tasks:
                action_tasks = self._extract_action_tasks(email_data)
                for action_task in action_tasks:
                    task = self.create_task(
                        task_list_id=task_list_id,
                        title=action_task['title'],
                        notes=action_task['notes'],
                        due_date=due_date,
                        default_due_time_utc=default_due_time_utc
                    )
                    if task:
                        created_tasks.append(task)

            logger.info(f"Created {len(created_tasks)} deadline-based tasks from email")
            return created_tasks

        except Exception as e:
            logger.error(f"Error creating tasks from email: {e}")
            return created_tasks

    def _extract_deadline_info(self, email_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract deadline information from email with enhanced pattern matching
        and context awareness.

        Args:
            email_data: Email data dictionary containing 'subject' and 'body' keys

        Returns:
            Dictionary with 'due_date' (YYYY-MM-DD) and 'description' of the deadline,
            or None if no valid deadline found
        """
        import re
        from datetime import datetime, timedelta
        from dateutil.parser import parse as parse_date

        def extract_dates(text):
            """Helper to extract dates from text using multiple patterns"""
            patterns = [
                # DD/MM/YYYY or DD-MM-YYYY (common in India/Europe)
                r'\b(\d{1,2}[-/]\d{1,2}[-/](?:20)?\d{2})\b',
                # ISO dates (YYYY-MM-DD, YYYY/MM/DD)
                r'\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b',
                # Month DD, YYYY
                r'\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+\d{1,2}(?:st|nd|rd|th)?[,\s]*\d{4})\b',
                # DD Month YYYY
                r'\b(\d{1,2}(?:st|nd|rd|th)?[\s,]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]*\d{4})\b',
                # Full month names
                r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)[\s,]+\d{1,2}(?:st|nd|rd|th)?[,\s]*\d{4})\b',
                # DD Month (without year)
                r'\b(\d{1,2}(?:st|nd|rd|th)?[\s]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)\b',
            ]
            
            dates = []
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                dates.extend(matches)
            return dates

        def parse_relative_date(date_str, email_datetime=None):
            """Parse relative date strings like 'tomorrow', 'next week', etc."""
            now = email_datetime or datetime.now()
            date_str = date_str.lower().strip()
            
            if date_str == 'today':
                return now.date()
            elif date_str == 'tomorrow':
                return (now + timedelta(days=1)).date()
            elif date_str == 'next week':
                return (now + timedelta(weeks=1)).date()
            elif date_str == 'next month':
                return (now + timedelta(days=30)).date()
            elif date_str.startswith('in ') and 'day' in date_str:
                try:
                    days = int(re.search(r'\d+', date_str).group())
                    return (now + timedelta(days=days)).date()
                except:
                    return None
            return None

        def parse_date_string(date_str):
            """Try to parse a date string in various formats"""
            # Handle DD/MM/YY or DD/MM/YYYY format
            for fmt in ['%d/%m/%y', '%d/%m/%Y', '%d-%m-%y', '%d-%m-%Y', 
                        '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%m-%d-%Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            
            # Try dateutil parser as fallback
            try:
                parsed = parse_date(date_str, dayfirst=True, fuzzy=True)
                if parsed:
                    # Handle missing year
                    if parsed.year == 1900 or parsed.year < 2020:
                        parsed = parsed.replace(year=datetime.now().year)
                        if parsed.date() < datetime.now().date():
                            parsed = parsed.replace(year=datetime.now().year + 1)
                    return parsed.date()
            except:
                pass
            return None

        # Get email content
        subject = email_data.get('subject', '')
        body = email_data.get('body', '')
        email_date = email_data.get('date')
        
        # Try to parse the email date for context
        email_datetime = None
        if email_date:
            try:
                email_datetime = parse_date(email_date)
            except:
                pass

        # Combine subject and body for analysis
        combined_text = f"{subject} {body}"
        
        # Normalize text: replace newlines with spaces for better matching
        normalized_text = re.sub(r'\s+', ' ', combined_text)
        
        # Look for important deadline-related phrases with context
        deadline_phrases = [
            # Common deadline phrases - allow any chars including what was newlines
            r'(?:deadline|due\s*(?:date)?|submit\s*by|register\s*(?:by|before)|last\s*(?:date|to\s+\w+)|closing\s*date|apply\s*by|expires?\s*on?|ends?\s*on?|before|until|no\s*later\s*than|not\s*after)\s*[:\-]?\s*(.{3,50})',
            # Event-based deadlines
            r'(?:hackathon|competition|internship|scholarship|conference|workshop|webinar|submission|application|registration)\s+(?:starts?|begins?|ends?|deadline|due|on|by|before)\s+(.{3,50})',
            # "Last to X is DATE" pattern - now on normalized text
            r'last\s+to\s+\w+(?:\s+\w+)?\s+(?:is|:)?\s*(.{3,30})',
        ]
        
        # First try: Extract dates directly from the entire text
        all_dates_in_text = extract_dates(normalized_text)
        if all_dates_in_text:
            logger.info(f"Found dates directly in text: {all_dates_in_text}")
        
        # Check for deadline phrases and extract potential dates
        potential_dates = []
        for pattern in deadline_phrases:
            for match in re.finditer(pattern, normalized_text, re.IGNORECASE):
                context = match.group(0)
                date_part = match.group(1) if match.lastindex else context
                
                # Extract all dates from the matched context
                dates_in_context = extract_dates(date_part)
                if dates_in_context:
                    for date_str in dates_in_context:
                        potential_dates.append({
                            'date_str': date_str,
                            'context': context
                        })
                else:
                    # The captured group might be a date itself
                    potential_dates.append({
                        'date_str': date_part.strip(),
                        'context': context
                    })
        
        # If no dates found in deadline phrases, use dates found anywhere in text
        if not potential_dates and all_dates_in_text:
            potential_dates = [{'date_str': d, 'context': f'Found date: {d}'} for d in all_dates_in_text]
        
        # Process and validate potential dates
        for item in potential_dates:
            date_str = item['date_str']
            context = item['context']
            
            # Skip if date_str is too short or too long
            if len(date_str) < 3 or len(date_str) > 50:
                continue
            
            # Try to parse as relative date first
            parsed_date = parse_relative_date(date_str, email_datetime)
            
            # If not a relative date, try parsing as absolute date
            if not parsed_date:
                parsed_date = parse_date_string(date_str)
            
            # Skip dates in the past (with 1-day grace period for timezone issues)
            if parsed_date and parsed_date >= (datetime.now().date() - timedelta(days=1)):
                # If we have a context, use it to create a better description
                description = context if context else f"Deadline: {date_str}"
                
                # Clean up the description
                description = re.sub(r'\s+', ' ', description).strip()
                if len(description) > 200:
                    description = description[:197] + '...'
                
                logger.info(f"Found deadline: {parsed_date} from '{date_str}' in context: {context[:50]}...")
                    
                return {
                    'due_date': parsed_date.strftime('%Y-%m-%d'),
                    'description': description
                }
        
        return None

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
