import pyodbc

# Replace these placeholders with your local research database settings.
server = 'SQL_SERVER_HOST'
database = 'ARIA_DATABASE_NAME'
username = 'RESEARCH_USERNAME'
password = 'RESEARCH_PASSWORD'

connection = pyodbc.connect(
    'DRIVER={SQL Server};'
    f'SERVER={server};'
    f'DATABASE={database};'
    f'UID={username};'
    f'PWD={password}'
)

cursor = connection.cursor()
