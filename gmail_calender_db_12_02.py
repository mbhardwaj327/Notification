import os
import datetime
import pickle
import base64
import csv
from collections import defaultdict
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from google.auth.exceptions import TransportError
from flask import Flask, jsonify, request
import pandas as pd
import mysql.connector

app = Flask(__name__)

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/calendar.readonly']

# Set your OpenAI API key as an environment variable
os.environ['OPENAI_API_KEY'] = 'your-api-key'

# Database credentials
DB_HOST = ""
DB_USER = ""
DB_PASSWORD = ""
DB_DATABASE = ""

def gmail_authenticate():
    """Authenticate the user and return the Gmail and Calendar service."""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    service = build('gmail', 'v1', credentials=creds)
    calendar_service = build('calendar', 'v3', credentials=creds)
    return service, calendar_service

def get_emails_from_inbox(service, user_id='me', max_results=50):
    """Fetches emails from the inbox from the last 7 days using Gmail API"""
    try:
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=2)).strftime('%Y/%m/%d')
        query = f'after:{yesterday}'
        results = service.users().messages().list(userId=user_id, labelIds=['INBOX'], q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])

        if not messages:
            print('No messages found.')
            return []

        email_data = []
        for msg in messages:
            email_data_raw = service.users().messages().get(userId=user_id, id=msg['id']).execute()
            payload = email_data_raw['payload']
            headers = payload['headers']
            subject = None
            sender = None
            date = None

            for header in headers:
                if header['name'] == 'Subject':
                    subject = header['value']
                if header['name'] == 'From':
                    sender = header['value']
                if header['name'] == 'Date':
                    date = header['value']

            body = None
            parts = payload.get('parts', [])
            for part in parts:
                if part['mimeType'] == 'text/plain':
                    body = base64.urlsafe_b64decode(part['body']['data']).decode()
                    break

            email_info = {
                'Date': date,
                'Subject': subject,
                'From': sender,
                'Body': body
            }

            email_data.append(email_info)

        return email_data

    except HttpError as error:
        print(f'An error occurred: {error}')
        return []
    except TransportError as transport_error:
        print(f'Transport error: {transport_error}')
        return []

def group_emails_by_subject(email_data):
    """Group emails by subject."""
    grouped_emails = defaultdict(list)
    for email in email_data:
        formatted_email = f"""
        Email: {email['Subject']}
        From: {email['From']}
        Date: {email['Date']}

        ---

        {email['Body']}
        """
        grouped_emails[email['Subject']].append(formatted_email)
    return grouped_emails

def save_grouped_emails_to_db(grouped_emails):
    """Save grouped emails to a MySQL database."""
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_DATABASE
        )
        cursor = connection.cursor()

        # Create table if it does not exist
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS grouped_emails (
            id INT AUTO_INCREMENT PRIMARY KEY,
            subject VARCHAR(255) NOT NULL,
            body TEXT NOT NULL
        )
        '''
        cursor.execute(create_table_query)

        # Insert grouped emails into the table
        for subject, bodies in grouped_emails.items():
            combined_body = "\n".join([body for body in bodies if body is not None])
            subject = subject if subject is not None else 'No Subject'
            insert_query = "INSERT INTO grouped_emails (subject, body) VALUES (%s, %s)"
            cursor.execute(insert_query, (subject, combined_body))

        # Commit the transaction
        connection.commit()

    except mysql.connector.Error as error:
        print(f"Failed to insert into MySQL table: {error}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def generate_notification_to_csv(grouped_emails):
    """Generate a notification based on grouped email data using GPT-4 via Langchain and save to CSV."""
    if not grouped_emails:
        print("No grouped email data provided for notification generation.")
        return

    template = """
    You are an assistant tasked with generating concise and actionable notifications based on provided email communications. Your role is to summarize the key points of the email and suggest the appropriate next steps, such as replying to an email, booking a flight, scheduling a meeting on the calendar, or other relevant actions.

    Using the provided email details:  
    - **Subject:** {subject}  
    - **Body:** {body}  

    Identify one of the following actions to take:  
    1. **Summary**  
    2. **Book Flight**  
    3. **Book Meeting on Calendar**  
    4. **Others**  

    Based on the chosen action, create a one-line notification in the following format:  
    ```  
    - action: chosen action,  
    - inputs_for_action: required inputs to take that action,  
    - notification: notification line
    ```  

    Ensure the notification is professional, clear, and easy to act upon.
    """
    prompt = PromptTemplate(input_variables=["subject", "body"], template=template)
    llm = ChatOpenAI(model_name="gpt-4o-mini")
    chain = prompt | llm

    with open('notifications.csv', mode='w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Subject', 'Notification']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for subject, bodies in grouped_emails.items():
            if len(bodies) > 0:
                combined_body = "\n".join(bodies)
                notification = chain.invoke({"subject": subject, "body": combined_body})
                writer.writerow({'Subject': subject, 'Notification': notification.content})
                print("Notification:")
                print(notification.content)
                print("="*50)

def get_calendar_events(calendar_service):
    """Fetch events from Google Calendar for the last 2 days."""
    try:
        now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        two_days_ago = (datetime.datetime.utcnow() - datetime.timedelta(days=10)).isoformat() + 'Z'

        events_result = calendar_service.events().list(
            calendarId='primary',
            timeMin=two_days_ago,
            timeMax=now,
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        if not events:
            print('No events found.')
            return []

        event_data = []
        for event in events:
            event_info = {
                'Summary': event.get('summary', 'No Title'),
                'Start': event['start'].get('dateTime', event['start'].get('date')),
                'End': event['end'].get('dateTime', event['end'].get('date')),
                'Location': event.get('location', 'No Location'),
                'Description': event.get('description', 'No Description')
            }
            event_data.append(event_info)

        return event_data

    except HttpError as error:
        print(f'An error occurred: {error}')
        return []

def save_calendar_events_to_db(events):
    """Save calendar events to a MySQL database."""
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_DATABASE
        )
        cursor = connection.cursor()

        # Create table if it does not exist
        create_table_query = '''
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INT AUTO_INCREMENT PRIMARY KEY,
            summary VARCHAR(255),
            start DATETIME,
            end DATETIME,
            location VARCHAR(255),
            description TEXT
        )
        '''
        cursor.execute(create_table_query)

        # Insert events into the table
        for event in events:
            insert_query = """
            INSERT INTO calendar_events (summary, start, end, location, description)
            VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (
                event['Summary'],
                event['Start'],
                event['End'],
                event['Location'],
                event['Description']
            ))

        # Commit the transaction
        connection.commit()

    except mysql.connector.Error as error:
        print(f"Failed to insert into MySQL table: {error}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/process_emails', methods=['GET','POST'])
def process_emails():
    try:
        max_results = 50
        service, calendar_service = gmail_authenticate()
        emails = get_emails_from_inbox(service, max_results=max_results)
        grouped_emails = group_emails_by_subject(emails)
        save_grouped_emails_to_db(grouped_emails)
        generate_notification_to_csv(grouped_emails)
        return jsonify({'message': 'Emails processed and notifications generated successfully.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process_calendar_events', methods=['GET', 'POST'])
def process_calendar_events():
    try:
        _, calendar_service = gmail_authenticate()
        events = get_calendar_events(calendar_service)
        save_calendar_events_to_db(events)
        return jsonify({'message': 'Calendar events retrieved and saved successfully.', 'events': events}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
