import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import base64
from email.mime.text import MIMEText
import logging
from sqlalchemy.orm import Session
from google_oauth_config import resolve_google_oauth_client_config

logger = logging.getLogger(__name__)

class GmailService:
    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build('gmail', 'v1', credentials=credentials, cache_discovery=False)

    @classmethod
    def from_user_token(cls, token_data: dict):
        """Create GmailService from user token data"""
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
                logger.info("Refreshed expired Gmail token")
            except Exception as e:
                logger.error(f"Failed to refresh Gmail token: {e}")
        return cls(credentials)

    def get_recent_emails(self, max_results: int = 10, days_back: int = 7, *, unread_only: bool = False, inbox_only: bool = False) -> List[Dict[str, Any]]:
        """
        Get recent emails from Gmail

        Args:
            max_results: Maximum number of emails to retrieve
            days_back: Look for emails from this many days back

        Returns:
            List of email dictionaries with subject, sender, body, etc.
        """
        try:
            # Calculate date filter
            date_filter = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y/%m/%d')

            # Build Gmail search query
            q_parts = [f'after:{date_filter}']
            if unread_only:
                q_parts.append('is:unread')
            if inbox_only:
                q_parts.append('in:inbox')
            q = ' '.join(q_parts)

            # Get messages
            results = self.service.users().messages().list(
                userId='me',
                maxResults=max_results,
                q=q
            ).execute()

            messages = results.get('messages', [])
            emails = []

            for message in messages:
                email_data = self._get_email_details(message['id'])
                if email_data:
                    emails.append(email_data)

            logger.info(f"Retrieved {len(emails)} recent emails (q='{q}')")
            return emails

        except Exception as e:
            logger.error(f"Error getting recent emails: {e}")
            return []

    def _get_email_details(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific email

        Args:
            message_id: Gmail message ID

        Returns:
            Email dictionary or None if error
        """
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            # Extract headers
            headers = message['payload']['headers']
            subject = self._get_header_value(headers, 'Subject')
            sender = self._get_header_value(headers, 'From')
            date = self._get_header_value(headers, 'Date')

            # Extract body
            body = self._get_email_body(message['payload'])

            return {
                'id': message_id,
                'subject': subject or 'No Subject',
                'sender': sender or 'Unknown',
                'date': date,
                'body': body,
                'snippet': message.get('snippet', ''),
                'thread_id': message.get('threadId')
            }

        except Exception as e:
            logger.error(f"Error getting email details for {message_id}: {e}")
            return None

    def _get_header_value(self, headers: List[Dict[str, str]], name: str) -> Optional[str]:
        """Get header value by name"""
        for header in headers:
            if header['name'].lower() == name.lower():
                return header['value']
        return None

    def _get_email_body(self, payload: Dict[str, Any]) -> str:
        """
        Extract email body from payload, prioritizing HTML.
        """
        def extract_part(payload_part: Dict[str, Any]) -> Optional[str]:
            mime_type = payload_part.get('mimeType')
            body_data = payload_part.get('body', {}).get('data')

            if mime_type == 'text/html' and body_data:
                return base64.urlsafe_b64decode(body_data).decode('utf-8')
            
            if mime_type == 'text/plain' and body_data:
                return base64.urlsafe_b64decode(body_data).decode('utf-8')

            if 'parts' in payload_part:
                # Try to find HTML part first
                for part in payload_part['parts']:
                    if part.get('mimeType') == 'text/html':
                        res = extract_part(part)
                        if res: return res
                
                # Fallback to any part
                for part in payload_part['parts']:
                    res = extract_part(part)
                    if res: return res
            
            return None

        content = extract_part(payload)
        return content if content else ""

    def mark_as_read(self, message_id: str) -> bool:
        """
        Mark email as read

        Args:
            message_id: Gmail message ID

        Returns:
            True if successful
        """
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            logger.info(f"Marked email {message_id} as read")
            return True
        except Exception as e:
            logger.error(f"Error marking email as read: {e}")
            return False

    def add_label(self, message_id: str, label_name: str) -> bool:
        """
        Add a label to an email

        Args:
            message_id: Gmail message ID
            label_name: Name of the label to add

        Returns:
            True if successful
        """
        try:
            # First get or create the label
            labels = self.service.users().labels().list(userId='me').execute()
            label_id = None

            for label in labels.get('labels', []):
                if label['name'].lower() == label_name.lower():
                    label_id = label['id']
                    break

            if not label_id:
                # Create new label
                label = self.service.users().labels().create(
                    userId='me',
                    body={'name': label_name, 'messageListVisibility': 'show', 'labelListVisibility': 'labelShow'}
                ).execute()
                label_id = label['id']

            # Add label to message
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [label_id]}
            ).execute()

            logger.info(f"Added label '{label_name}' to email {message_id}")
            return True

        except Exception as e:
            logger.error(f"Error adding label: {e}")
            return False
