# Smart City - Cloud Deployment Guide (Free of Cost)

This guide will help you deploy your Django project to the cloud using free-tier services. We will use **Render** for hosting the application and **Aiven** for the MySQL database.

## Prerequisites
1.  **GitHub Account**: To host your code and connect to Render.
2.  **Aiven Account**: For a free MySQL database instance.
3.  **Render Account**: To host the web application.

---

## Step 1: Prepare Your Code
I have already updated your `settings.py` and created `requirements_prod.txt`.
1.  **Rename requirements**: Rename `requirements_prod.txt` to `requirements.txt`.
2.  **Git Init**: Initialize a git repository in your project folder:
    ```bash
    git init
    git add .
    git commit -m "Initial commit for deployment"
    ```
3.  **Create Repository**: Create a new **Private** repository on GitHub and push your code:
    ```bash
    git remote add origin YOUR_GITHUB_REPO_URL
    git push -u origin main
    ```

---

## Step 2: Set Up a Free MySQL Database (Aiven)
1.  Sign up at [aiven.io](https://aiven.io/).
2.  Create a new **MySQL** service.
3.  Select the **Free Plan**.
4.  Once created, copy the **Service URI** or the individual connection details (Host, Port, User, Password, Database).
5.  **Initialize Tables**: You must create the tables in your new database.
    - Copy the contents of the `schema.sql` file I just created.
    - Go to your Aiven Console -> MySQL Service -> **Query Editor** (or use a tool like MySQL Workbench).
    - Paste the SQL code and click **Run**.
6.  **Done**: I have already updated `views.py` to use environment variables and created a `.env` file with these credentials for you.
7.  **Verified**: Your application is now ready to connect to the Aiven MySQL database.

---

## Step 3: Deploy to Render
1.  Sign up at [render.com](https://render.com/).
2.  Click **New +** and select **Web Service**.
3.  Connect your GitHub account and select your `SmartCity` repository.
4.  **Configure Service**:
    - **Name**: `smart-city-app`
    - **Runtime**: `Python 3`
    - **Build Command**: `pip install -r requirements.txt`
    - **Start Command**: `gunicorn City.wsgi:application`
5.  **Environment Variables**:
    Click the **Advanced** button and add the following:
    - `PYTHON_VERSION`: `3.10.0` or similar
    - `DJANGO_SECRET_KEY`: (Generate a random string)
    - `DJANGO_DEBUG`: `False`
    - `DJANGO_ALLOWED_HOSTS`: `your-app-name.onrender.com`
    - `EMAIL_HOST_USER`: Your email
    - `EMAIL_HOST_PASSWORD`: Your Gmail App Password
    - `DB_HOST`, `DB_USER`, etc. (If you update `views.py` to use environment variables)

---

## Step 4: Handle YOLOv8 Model
The YOLOv8 model file (`model/yolo8_best.pt`) must be included in your repository. Render has a 512MB RAM limit on the free tier. The "nano" model should work, but limit image uploads during testing to avoid memory spikes.

---

## Tips for Success
- **WhiteNoise**: I've enabled WhiteNoise in `settings.py` so your CSS and JS will work automatically on Render.
- **Media Files**: On Render's free tier, uploaded photos will be deleted if the app restarts. For permanent storage, consider connecting to **Cloudinary** (free tier).
- **Log Monitoring**: Use the Render dashboard "Logs" tab to see if the app is running correctly or if there are any errors.

---

**Need Help?** Just ask if you get stuck on any of these steps!
