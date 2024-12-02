# Notification
This Flask application integrates with Gmail and Google Calendar to fetch recent emails and events, stores them in a MySQL database, and generates notifications using GPT-4. It offers REST API endpoints for processing email and calendar data seamlessly.

# Flask Gmail and Calendar Integration

## Overview

This project is a Flask-based application that connects to Gmail and Google Calendar to retrieve emails and calendar events from the past two days. It stores the data in a MySQL database and uses GPT-4 to generate actionable notifications for the emails. The application provides REST API endpoints to process the data efficiently.

## Features
- **Gmail Integration**: Fetch and process recent Gmail emails.
- **Google Calendar Integration**: Retrieve and store recent calendar events.
- **Email Notifications**: Generate actionable notifications using GPT-4.
- **REST API Endpoints**: Easily interact with the email and calendar data.

## Installation
1. **Clone the Repository**
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Install Required Libraries**
   Install all the dependencies using pip:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set Up Google API Credentials**
   - Download your `client_secret.json` file from the Google Developer Console.
   - Place it in the project root directory.

4. **Set Up Environment Variables**
   Set your OpenAI API key as an environment variable:
   ```bash
   export OPENAI_API_KEY='your_openai_api_key'
   ```

5. **Database Setup**
   Ensure you have a MySQL database running and update the database credentials in the script accordingly.

## Usage

### Running the Application
Start the Flask application by running:
```bash
python app.py
```

The server will start in debug mode by default.

### API Endpoints
1. **Process Emails**: `/process_emails` (GET/POST)
   - Fetches emails from Gmail, groups them by subject, saves them to the database, and generates notifications.

2. **Process Calendar Events**: `/process_calendar_events` (GET/POST)
   - Fetches events from Google Calendar for the last 2 days and saves them to the database.

## Notes
- The Google API scopes are set to readonly, ensuring that the application cannot modify emails or calendar events.
- Keep your `client_secret.json` and API keys secure.

Feel free to explore, contribute, and improve this project!

