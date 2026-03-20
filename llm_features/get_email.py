from gmail_client import GmailClient
import base64
def get_email_content(email_id):
    gmail_service, _ = GmailClient.authenticate()
    message = gmail_service.users().messages().get(userId='me', id=email_id).execute()
    subject = next(h['value'] for h in message['payload']['headers'] if h['name'] == 'Subject')
    parts = message['payload'].get('parts', [])
    body = ""
    for part in parts:
        if part['mimeType'] == 'text/plain':
            body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            break
    print(f"Subject: {subject}")
    print(f"Body: {body[:200]}...")
get_email_content("198bd511ab402e4b")