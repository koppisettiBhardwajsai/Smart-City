-- Smart City Civic Platform - Final Corrected Database Schema
-- IMPORTANT: This script will DROP existing tables and recreate them with the correct column names.
-- Copy and Run this in your Aiven MySQL Query Editor.

DROP TABLE IF EXISTS complaint;
DROP TABLE IF EXISTS fieldofficer;
DROP TABLE IF EXISTS municipality;
DROP TABLE IF EXISTS signup;

-- 1. Table for Citizen Registration
CREATE TABLE signup (
    username VARCHAR(500) PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    contact_no VARCHAR(100),
    email_id VARCHAR(500),
    address TEXT
);

-- 2. Table for Municipal Departments
CREATE TABLE municipality (
    municipality_name VARCHAR(500) PRIMARY KEY,
    city_name VARCHAR(500),
    employee_name VARCHAR(500),
    municipality_contact_no VARCHAR(100),
    employee_contact_no VARCHAR(100),
    username VARCHAR(500) UNIQUE,
    password VARCHAR(500) NOT NULL,
    municipality_desc TEXT
);

-- 3. Table for Field Officers
CREATE TABLE fieldofficer (
    username VARCHAR(500) PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    contact_no VARCHAR(100),
    municipality_name VARCHAR(500),
    FOREIGN KEY (municipality_name) REFERENCES municipality(municipality_name) ON DELETE CASCADE
);

-- 4. Table for Citizen Complaints
CREATE TABLE complaint (
    complaint_id INT PRIMARY KEY,
    citizenname VARCHAR(500),
    description TEXT,
    category VARCHAR(500),
    latitude VARCHAR(200),
    longitude VARCHAR(200),
    complaint_date DATE,
    municipality_name VARCHAR(500),
    priority VARCHAR(100),
    severity VARCHAR(100),
    cost VARCHAR(100),
    photo VARCHAR(500),
    assigned_to VARCHAR(500),
    status VARCHAR(100) DEFAULT 'Pending',
    FOREIGN KEY (citizenname) REFERENCES signup(username) ON DELETE SET NULL,
    FOREIGN KEY (municipality_name) REFERENCES municipality(municipality_name) ON DELETE SET NULL
);
