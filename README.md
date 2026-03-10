# Smart City Application - Setup & User Manual

Welcome to the Smart City Application project. This guide will help you set up the environment, configure the database, and run the application successfully.

## 1. Prerequisites
Before you begin, ensure you have the following installed on your system:
- **Python (3.8 or higher)**: [Download Python](https://www.python.org/downloads/)
- **MySQL Server**: [Download MySQL](https://dev.mysql.com/downloads/installer/)

## 2. Database Setup
The application uses a MySQL database to store user and complaint data.

1.  Open your MySQL Command Line Client or a tool like MySQL Workbench.
2.  Login as `root`.
3.  Copy and execute the commands from the **`DB.txt`** file found in the project folder to create the database and tables.
    - *Note: This will create a database named `smartcity`.*

### **Important: Database Configuration**
The application is configured to connect to MySQL with the following credentials by default:
- **Host**: `127.0.0.1` (Localhost)
- **Port**: `3306`
- **User**: `root`
- **Password**: `Database password of your laptop`
- **Database**: `smartcity`

**If your MySQL password is different:**
1.  Open `CityApp/views.py`.
2.  Locate the `DB_CONFIG` dictionary (around line 22).
3.  Update the `'password'` field to match your local MySQL root password.

## 3. Environment Setup
**The project is distributed without the virtual environment to save space.**
You need to set it up before running the project.

**Automatic Setup (Recommended):**
1.  Double-click **`setup.bat`** in the project folder.
2.  Wait for it to create the environment and install all libraries.
3.  Once finished, you are ready to run the app.

**Manual Setup:**
If the script doesn't work, open a terminal in the folder and run:
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install cryptography
```

## 4. Running the Application
Once setup is complete:

**Option 1: Double-Click Script**
- Locate the file **`run_venv.bat`** in the project folder.
- Double-click it.
- A terminal window will open, and the server will start.

**Option 2: Command Line**
- Open a terminal in the project folder.
- Run:
  ```powershell
  .\run_venv.bat
  ```

Once the server is running, open your web browser and go to:
**http://127.0.0.1:8000/**

## 5. Usage Guide
### Login Credentials
- **Admin Login**:
  - Username: `admin`
  - Password: `admin`
- **Municipality/Officer/User**: You must register these accounts or create them through the Admin/Municipality dashboards first.

### Features
- **Admin**: Create Municipality departments, View Users/Complaints/Municipalities.
- **User**: Register, Log in, Report Complaints (with image upload & auto-detection), View Status.
- **Municipality**: Log in, Add Field Officers, Assign Complaints to Officers.
- **Field Officer**: Log in, View Assigned Tasks, Update Status (Close complaints).

## Troubleshooting
- **"ModuleNotFoundError"**: Make sure you are using `run_venv.bat` to start the server.
- **"RuntimeError: cryptography is required"**: We have already installed this, but if it reappears, run `.venv\Scripts\python.exe -m pip install cryptography`.
- **Database Errors**: Ensure MySQL service is running and the credentials in `views.py` match your MySQL setup.
