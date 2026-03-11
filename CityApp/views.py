import matplotlib
matplotlib.use('Agg')
from django.shortcuts import render, redirect
from django.template import RequestContext
from django.contrib import messages
import pymysql
from django.http import HttpResponse
from django.core.files.storage import FileSystemStorage
from datetime import date
import os
import exifread
import base64
import io
import json
from django.core.mail import send_mail
from django.conf import settings
from dotenv import load_dotenv

load_dotenv()

# Global session variables replaced by Django session framework
# request.session['uname'] -> Citizen/Admin username
# request.session['mname'] -> Municipality name
# request.session['oname'] -> Officer username

DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'BhardwajSai@123'),
    'database': os.getenv('DB_NAME', 'smartcity'),
    'charset': 'utf8',
    'ssl': {'ssl_mode': 'REQUIRED'} if os.getenv('DB_SSL', 'False') == 'True' else None
}

CONFIDENCE_THRESHOLD = 0.35
GREEN = (0, 255, 0)
# Deferred model loading to prevent startup hangs on limited hardware (like Render free tier)
_yolo8_model = None
def get_yolo_model():
    global _yolo8_model
    if _yolo8_model is None:
        try:
            from ultralytics import YOLO  # Lazy import
            _yolo8_model = YOLO("model/yolo8_best.pt")
        except Exception as e:
            print(f"Error loading YOLO model: {e}")
    return _yolo8_model

# Helper function to send email notifications for complaint lifecycle events
def _send_complaint_update_email(complaint_id, subject, event_description):
    try:
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            # Get complaint details and citizen email in one join or sequential calls
            cur.execute(f"select description, citizenname FROM complaint where complaint_id='{complaint_id}'")
            comp_row = cur.fetchone()
            if comp_row:
                desc, citizen_name = comp_row
                cur.execute(f"select email_id FROM signup where username='{citizen_name}'")
                email_row = cur.fetchone()
                if email_row and email_row[0]:
                    recipient_email = email_row[0]
                    message = f"Dear {citizen_name},\n\nYour complaint #{complaint_id} has been updated.\n\nDescription: {desc}\n\nUpdate: {event_description}\n\nRegards,\nSmartCity Team"
                    send_mail(subject, message, settings.EMAIL_HOST_USER, [recipient_email], fail_silently=True)
                    print(f"Email sent to {recipient_email} for complaint #{complaint_id}")
    except Exception as e:
        print(f"Email Helper Error: {e}")

# function to read test image and then detect & predict road damage type
def predictDamage(path):
    import cv2  # Lazy import
    import numpy as np  # Lazy import
    
    cost = 0
    frame = cv2.imread(path)
    if frame is None:
        return "", "Unknown", "0"
        
    # Resize image to save RAM (Render Free Tier limit is 512MB)
    # Most mobile photos are 3000px+, which can use 100MB+ of RAM
    h, w = frame.shape[:2]
    max_dim = 640
    if h > max_dim or w > max_dim:
        scale = max_dim / max(h, w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        
    model = get_yolo_model()
    if model is None:
        return "", "Unknown", "0"
        
    detections = model(frame)[0]
    result = 0
    counter = 0
    
    for data in detections.boxes.data.tolist():
        confidence = data[4]
        if float(confidence) >= CONFIDENCE_THRESHOLD:
            xmin, ymin, xmax, ymax = int(data[0]), int(data[1]), int(data[2]), int(data[3])
            cv2.rectangle(frame, (xmin, ymin) , (xmax, ymax), GREEN, 2)
            cv2.putText(frame, "Damage", (xmin, ymin),  cv2.FONT_HERSHEY_SIMPLEX,0.7, (255, 0, 0), 2)
            result = 1
            counter += 1
            w_box = (xmax + ymax) / 2
            cost += w_box * 100
            
    if result == 0:
        cv2.putText(frame, 'No Damage Detected', (50, 100),  cv2.FONT_HERSHEY_SIMPLEX,0.7, (255, 0, 0), 2)
    
    severity = "High" if counter >= 3 else "Low"
    if cost == 0:
        cost = 100000
        
    # More memory-efficient encoding than plt.savefig
    _, buffer = cv2.imencode('.png', frame)
    img_b64 = base64.b64encode(buffer).decode('utf-8')
    
    # Explicit cleanup
    del frame
    del buffer
    
    return img_b64, severity, str(int(cost))

def _get_if_exist(data, key):
    if key in data:
        return data[key]

    return None

def _convert_to_degress(value):
    """
    Helper function to convert the GPS coordinates stored in the EXIF to degress in float format
    :param value:
    :type value: exifread.utils.Ratio
    :rtype: float
    """
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)

    return d + (m / 60.0) + (s / 3600.0)
    
def get_exif_location(exif_data):
    """
    Returns the latitude and longitude, if available, from the provided exif_data (obtained through get_exif_data above)
    """
    lat = "Not Found"
    lon = "Not Found"
    gps_latitude = _get_if_exist(exif_data, 'GPS GPSLatitude')
    gps_latitude_ref = _get_if_exist(exif_data, 'GPS GPSLatitudeRef')
    gps_longitude = _get_if_exist(exif_data, 'GPS GPSLongitude')
    gps_longitude_ref = _get_if_exist(exif_data, 'GPS GPSLongitudeRef')

    if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
        lat = _convert_to_degress(gps_latitude)
        if gps_latitude_ref.values[0] != 'N':
            lat = 0 - lat

        lon = _convert_to_degress(gps_longitude)
        if gps_longitude_ref.values[0] != 'E':
            lon = 0 - lon

    return str(lat), str(lon)

def get_exif_data(image_file):
    with open(image_file, 'rb') as f:
        exif_tags = exifread.process_file(f)
    return exif_tags

def UpdateStatus(request):
    if request.method == 'GET':
        oname = request.session.get('oname')
        if oname is None:
            return render(request, 'OfficerLogin.html', {'data': 'Please login first'})
        
        tid = request.GET.get('tid', False)
        status = "Closed"
        
        # Send Notification Email using helper
        _send_complaint_update_email(tid, f"SmartCity: Complaint #{tid} Resolved", f"The issue has been successfully resolved/closed.")

        db_connection = pymysql.connect(**DB_CONFIG)
        db_cursor = db_connection.cursor()
        student_sql_query = "update complaint set status='"+status+"' where complaint_id='"+tid+"'"
        db_cursor.execute(student_sql_query)
        db_connection.commit()
        output = f'<div class="status-banner success slide-in">Complaint status successfully updated: <strong>{status}</strong></div>'
        context= {'data':output}
        return render(request, 'OfficerScreen.html', context)

def ViewTask(request):
    if request.method == 'GET':
        oname = request.session.get('oname')
        if oname is None:
            return render(request, 'OfficerLogin.html', {'data': 'Please login first'})
        output = '<div class="table-container fade-in"><table class="data-table"><thead><tr>'
        output += '<th>ID</th><th>Citizen</th><th>Description</th><th>Category</th>'
        output += '<th>Location</th><th>Date</th><th>Municipality</th>'
        output += '<th>Priority</th><th>Severity</th><th>Cost</th><th>Evidence</th>'
        output += '<th>Status</th><th>Action</th></tr></thead><tbody>'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select * from complaint where assigned_to='"+oname+"' and status='Pending'")
            rows = cur.fetchall()
            for row in rows:
                output += f'<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td>'
                output += f'<td><small>{row[4]},<br/>{row[5]}</small></td><td>{row[6]}</td><td>{row[7]}</td>'
                output += f'<td>{row[8]}</td><td>{row[9]}</td><td>{row[10]}</td>'
                output += f'<td><img src="/static/photo/{row[11]}" style="width:80px;height:80px;object-fit:cover;border-radius:8px;box-shadow:var(--shadow-sm);"/></td>'
                output += f'<td><span class="badge info">{row[13]}</span></td>'
                output += f'<td><a href="UpdateStatus?tid={row[0]}" style="display:inline-block; background:linear-gradient(135deg, #00b09b 0%, #96c93d 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">Mark Closed</a></td></tr>'
        output += "</tbody></table></div>"
        context= {'data':output}
        return render(request, 'OfficerScreen.html', context)

def AssignedToAction(request):
    if request.method == 'POST':
        mname = request.session.get('mname')
        if mname is None:
            return render(request, 'MunicipalityLogin.html', {'data': 'Please login first'})
        complaint = request.POST.get('t1', False)
        emp = request.POST.get('t2', False)
        db_connection = pymysql.connect(**DB_CONFIG)
        db_cursor = db_connection.cursor()
        student_sql_query = "update complaint set assigned_to='"+emp+"' where complaint_id='"+complaint+"'"
        db_cursor.execute(student_sql_query)
        db_connection.commit()
        print(db_cursor.rowcount, "Record Inserted")
        if db_cursor.rowcount == 1:
            status = f'<div class="status-banner success slide-in">Work successfully assigned to: <strong>{emp}</strong></div>'
            # Send Notification Email using helper
            _send_complaint_update_email(complaint, f"SmartCity: Officer Assigned to Complaint #{complaint}", f"A field officer ({emp}) has been assigned to address your grievance.")
            
        context= {'data':status}
        return render(request, 'MunicipalityScreen.html', context)

def AssignedTo(request):
    if request.method == 'GET':
        mname = request.session.get('mname')
        if mname is None:
            return render(request, 'MunicipalityLogin.html', {'data': 'Please login first'})
        output = '<tr><td><label>Complaint ID</label></td><td><select name="t1">'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select complaint_id from complaint where municipality_name='"+mname+"' and assigned_to='-'")
            rows = cur.fetchall()
            for row in rows:
                output += '<option value="'+str(row[0])+'">'+str(row[0])+'</option>'
        output += "</select></td></tr>"
        
        output += '<tr><td><label>Field Officer</label></td><td><select name="t2">'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select username from fieldofficer where municipality_name='"+mname+"'")
            rows = cur.fetchall()
            for row in rows:
                output += '<option value="'+row[0]+'">'+row[0]+'</option>'
        output += "</select></td></tr>"
        
        context= {'data1':output}
        return render(request, 'AssignedTo.html', context)

def ComplaintRequest(request):
    if request.method == 'GET':
        mname = request.session.get('mname')
        if mname is None:
            return render(request, 'MunicipalityLogin.html', {'data': 'Please login first'})
        output = '<div class="table-container fade-in"><table class="data-table"><thead><tr>'
        output += '<th>ID</th><th>Citizen</th><th>Description</th><th>Category</th>'
        output += '<th>Location</th><th>Date</th><th>Municipality</th>'
        output += '<th>Priority</th><th>Severity</th><th>Cost</th><th>Evidence</th>'
        output += '<th>Status</th><th>Action</th></tr></thead><tbody>'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select * from complaint where municipality_name='"+mname+"' and status='Pending'")
            rows = cur.fetchall()
            for row in rows:
                output += f'<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td>'
                output += f'<td><small>{row[4]},<br/>{row[5]}</small></td><td>{row[6]}</td><td>{row[7]}</td>'
                output += f'<td>{row[8]}</td><td>{row[9]}</td><td>{row[10]}</td>'
                output += f'<td><img src="/static/photo/{row[11]}" style="width:80px;height:80px;object-fit:cover;border-radius:8px;"/></td>'
                output += f'<td><span class="badge warning">{row[13]}</span></td>'
                output += f'<td><a href="AssignedTo?tid={row[0]}" style="display:inline-block; background:linear-gradient(135deg, #4361ee 0%, #3a0ca3 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">Assign Officer</a></td></tr>'
        output += "</tbody></table></div>"
        context= {'data':output}
        return render(request, 'MunicipalityScreen.html', context)

def ViewGrievanceStatus(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname is None:
            return render(request, 'UserLogin.html', {'data': 'Please login first'})
            
        output = '<div class="table-container fade-in"><table class="data-table"><thead><tr>'
        output += '<th>ID</th><th>Description</th><th>Category</th>'
        output += '<th>Location</th><th>Date</th><th>Municipality</th>'
        output += '<th>Priority</th><th>Severity</th><th>Est. Cost</th>'
        output += '<th>Evidence</th><th>Assignment</th><th>Status</th><th>Actions</th></tr></thead><tbody>'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select * from complaint")
            rows = cur.fetchall()
            for row in rows:
                if row[1] == uname:
                    output += f'<tr><td>{row[0]}</td><td>{row[2]}</td><td>{row[3]}</td>'
                    output += f'<td><small>{row[4]},<br/>{row[5]}</small></td><td>{row[6]}</td><td>{row[7]}</td>'
                    output += f'<td>{row[8]}</td><td>{row[9]}</td><td>{row[10]}</td>'
                    output += f'<td><img src="/static/photo/{row[11]}" style="width:80px;height:80px;object-fit:cover;border-radius:8px;"/></td>'
                    output += f'<td>{row[12]}</td><td><span class="badge info">{row[13]}</span></td>'
                    output += f'<td><a href="javascript:void(0);" onclick="confirmDelete({row[0]})" style="display:inline-block; background:linear-gradient(135deg, #ef476f 0%, #d63654 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-trash"></i></a></td></tr>'
        output += "</tbody></table></div>"
        
        # Add JavaScript for delete confirmation
        output += """
        <script>
        function confirmDelete(complaintId) {
            if (confirm('Are you sure you want to delete this complaint? This action cannot be undone.')) {
                window.location.href = 'DeleteComplaint?cid=' + complaintId;
            }
        }
        </script>
        """
        
        context= {'data':output}
        return render(request, 'UserScreen.html', context)

def DeleteComplaint(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname is None:
            return render(request, 'UserLogin.html', {'data': 'Please login first'})

        cid = request.GET.get('cid', False)
        
        if not cid:
            status = '<div class="status-banner error slide-in">Invalid complaint ID.</div>'
            context= {'data':status}
            if uname == 'admin':
                return render(request, 'AdminScreen.html', context)
            return render(request, 'UserScreen.html', context)
        
        # Verify ownership and get photo filename
        con = pymysql.connect(**DB_CONFIG)
        photo_filename = None
        is_owner = False
        
        with con:
            cur = con.cursor()
            cur.execute("select citizenname, photo from complaint where complaint_id='"+cid+"'")
            rows = cur.fetchall()
            for row in rows:
                if row[0] == uname or uname == 'admin':
                    is_owner = True
                    photo_filename = row[1]
                    break
        
        if not is_owner:
            status = '<div class="status-banner error slide-in">You can only delete your own complaints.</div>'
            context= {'data':status}
            if uname == 'admin':
                return render(request, 'AdminScreen.html', context)
            return render(request, 'UserScreen.html', context)
        
        # Delete photo file if exists
        if photo_filename:
            photo_path = 'CityApp/static/photo/' + photo_filename
            if os.path.exists(photo_path):
                try:
                    os.remove(photo_path)
                except Exception as e:
                    print(f"Error deleting photo: {e}")
        
        # Delete from database
        db_connection = pymysql.connect(**DB_CONFIG)
        db_cursor = db_connection.cursor()
        delete_query = "DELETE FROM complaint WHERE complaint_id='"+cid+"';"
        db_cursor.execute(delete_query)
        db_connection.commit()
        
        if db_cursor.rowcount == 1:
            # Send Notification Email using helper BEFORE deletion logic is fully gone or use cached info
            # In this app, we already have the info from the 'is_owner' check loop
            _send_complaint_update_email(cid, f"SmartCity: Complaint #{cid} Deleted", f"Your complaint has been removed from the system.")
            if uname == 'admin':
                return redirect('ViewUserComplaint')
            return redirect('ViewGrievanceStatus')
        else:
            status = '<div class="status-banner error slide-in">Failed to delete complaint. Please try again.</div>'
        
        context= {'data':status}
        if uname == 'admin':
            return render(request, 'AdminScreen.html', context)
        return render(request, 'UserScreen.html', context)


def ReportComplaintAction(request):
    if request.method == 'POST':
        try:
            uname = request.session.get('uname')
            if uname is None:
                return render(request, 'UserLogin.html', {'data': 'Please login first'})
            desc = request.POST.get('t1', False)
            category = request.POST.get('t2', False)
            municipality = request.POST.get('t3', False)
            priority = request.POST.get('t4', False)
            
            if 't5' not in request.FILES:
                return render(request, 'UserScreen.html', {'data': '<div class="status-banner error">Please upload a photo.</div>'})
                
            photo_file = request.FILES['t5']
            photo = photo_file.read()
            filename = photo_file.name
            ext = filename.split(".")[-1]
            
            ticket = 1
            con = pymysql.connect(**DB_CONFIG)
            with con:
                cur = con.cursor()
                cur.execute("select max(complaint_id) from complaint")
                row = cur.fetchone()
                if row and row[0]:
                    ticket = int(row[0]) + 1
            
            # Ensure directory exists (Ephemeral on Render!)
            upload_dir = os.path.join('CityApp', 'static', 'photo')
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)
                
            file_path = os.path.join(upload_dir, f"{ticket}.{ext}")
            with open(file_path, "wb") as file:
                file.write(photo)
            
            # AI & Metadata processing
            try:
                lat, long = get_exif_location(get_exif_data(file_path))
            except:
                lat, long = "0.0", "0.0"
                
            try:
                img, severity, cost = predictDamage(file_path)
            except Exception as e:
                print(f"AI Processing Error: {e}")
                img, severity, cost = "", "Low", "0"
            
            status = "Error in logging your complaint. Please try after sometime"   
            db_connection = pymysql.connect(**DB_CONFIG)
            with db_connection:
                db_cursor = db_connection.cursor()
                query = "INSERT INTO complaint (complaint_id, citizenname, description, category, latitude, longitude, complaint_date, municipality_name, priority, severity, cost, photo, assigned_to, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                data = (ticket, uname, desc, category, lat, long, date.today(), municipality, priority, severity, cost, f"{ticket}.{ext}", "-", "Pending")
                db_cursor.execute(query, data)
                db_connection.commit()
                
            if db_cursor.rowcount == 1:
                status = f'<div class="status-banner success slide-in"><h4>Complaint Registered</h4><p>ID: <strong>#{ticket}</strong> | Assigned: <strong>{municipality}</strong></p></div>'
                if category == "Road Damage":
                    status = status.replace('</div>', f'<span class="badge info">Automatic Estimated Cost: {cost}</span></div>')
                
                # Async-ish email (ignore errors to prevent 500)
                try:
                    event_desc = f"Successfully registered and assigned to {municipality}."
                    if category == "Road Damage":
                        event_desc += f" Estimated cost: {cost}"
                    _send_complaint_update_email(ticket, f"SmartCity: Complaint #{ticket} Registered", event_desc)
                except:
                    pass
                    
            context= {'data':status, 'img': img}
            return render(request, 'UserScreen.html', context)
            
        except Exception as e:
            print(f"CRITICAL ERROR in ReportComplaintAction: {e}")
            import traceback
            traceback.print_exc()
            return render(request, 'UserScreen.html', {'data': f'<div class="status-banner error">Something went wrong: {str(e)}</div>'})

def ReportComplaint(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname is None:
            return render(request, 'UserLogin.html', {'data': 'Please login first'})
        output = '<tr><td><label>Department</label></td><td><select name="t3">'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select municipality_name from municipality")
            rows = cur.fetchall()
            for row in rows:
                output += '<option value="'+row[0]+'">'+row[0]+'</option>'
        output += "</select></td></tr>"        
        context= {'data1':output}
        return render(request, 'ReportComplaint.html', context)
def getCount(category):
    count = 0
    con = pymysql.connect(**DB_CONFIG)
    with con:
        cur = con.cursor()
        cur.execute("select count(category) from complaint where category='"+category+"'")
        rows = cur.fetchall()
        for row in rows:
            count = row[0]
            break
    return count 

def Graph(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
        analytics_data = {
            'categories': {},
            'statuses': {},
            'severities': {},
            'municipalities': {},
            'total_complaints': 0,
            'total_cost': 0,
            'recent_activity': []
        }
        
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            
            # Fetch all complaints for aggregation and filtering
            cur.execute("select category, status, severity, municipality_name, cost, description, complaint_date, priority, complaint_id from complaint")
            rows = cur.fetchall()
            analytics_data['total_complaints'] = len(rows)
            
            complaints_list = []
            total_cost_calc = 0
            for row in rows:
                cat, status, sev, muni, cost, desc, cdate, priority, cid = row
                
                # Clean up values
                cat_val = str(cat) if cat else "Uncategorized"
                status_val = str(status) if status else "Pending"
                sev_val = str(sev) if sev else "Low"
                muni_val = str(muni) if muni else "General"
                priority_val = str(priority) if priority else "Low"
                
                # Raw list for client-side filtering
                complaints_list.append({
                    'id': cid,
                    'category': cat_val,
                    'status': status_val,
                    'severity': sev_val,
                    'priority': priority_val,
                    'municipality': muni_val,
                    'cost': str(cost),
                    'desc': str(desc)[:60],
                    'date': str(cdate)
                })

                # Initial aggregation for cards
                analytics_data['categories'][cat_val] = analytics_data['categories'].get(cat_val, 0) + 1
                analytics_data['statuses'][status_val] = analytics_data['statuses'].get(status_val, 0) + 1
                
                try:
                    if cost and cost != '-':
                        cost_val = "".join(filter(str.isdigit, str(cost)))
                        if cost_val:
                            total_cost_calc += int(cost_val)
                except:
                    pass
            
            analytics_data['complaints_list'] = complaints_list
            analytics_data['total_cost'] = total_cost_calc
            analytics_data['pending_count'] = analytics_data['statuses'].get('Pending', 0)
            analytics_data['resolved_count'] = analytics_data['statuses'].get('Closed', 0)
            
            # Recent activity
            analytics_data['recent_activity'] = complaints_list[:5]

        context = {
            'analytics_data': analytics_data,
            'total_complaints': analytics_data['total_complaints'],
            'pending_count': analytics_data['pending_count'],
            'resolved_count': analytics_data['resolved_count'],
            'total_cost': analytics_data['total_cost']
        }
        return render(request, 'Analytics.html', context)
                         
        


def AddOfficerAction(request):
    if request.method == 'POST':
        mname = request.session.get('mname')
        if mname is None:
            return render(request, 'MunicipalityLogin.html', {'data': 'Please login first'})
        username = request.POST.get('t1', False)
        password = request.POST.get('t2', False)
        contact = request.POST.get('t3', False)
        status = 'none'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("insert into fieldofficer values('"+username+"','"+password+"','"+contact+"','"+mname+"')")
            con.commit()
            if cur.rowcount == 1:
                status = f'<div class="status-banner success slide-in">Field Officer <strong>{username}</strong> registered successfully.</div>'
        context= {'data':status}
        return render(request, 'MunicipalityScreen.html', context)

def AddOfficer(request):
    if request.method == 'GET':
        return render(request, 'AddOfficer.html', {})

def ViewOfficer(request):
    if request.method == 'GET':
        mname = request.session.get('mname')
        if mname is None:
            return render(request, 'MunicipalityLogin.html', {'data': 'Please login first'})
        output = '<div class="table-container fade-in"><table class="data-table"><thead><tr>'
        output += '<th>Username</th><th>Contact No</th><th>Municipality</th><th>Actions</th></tr></thead><tbody>'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute(f"select * from fieldofficer where municipality_name='{mname}'")
            rows = cur.fetchall()
            for row in rows:
                output += f'<tr><td>{row[0]}</td><td>{row[2]}</td><td>{row[3]}</td>'
                output += f'<td><a href="UpdateOfficer?user={row[0]}" style="display:inline-block; background:linear-gradient(135deg, #00b09b 0%, #96c93d 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; margin-right:20px; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-edit"></i></a>'
                output += f'<a href="javascript:void(0);" onclick="confirmDelete(\'{row[0]}\')" style="display:inline-block; background:linear-gradient(135deg, #ef476f 0%, #d63654 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-trash"></i></a></td></tr>'
        output += "</tbody></table></div>"
        
        # Add JavaScript for delete confirmation
        output += """
        <script>
        function confirmDelete(username) {
            if (confirm('Are you sure you want to delete this officer? This action cannot be undone.')) {
                window.location.href = 'DeleteOfficer?user=' + username;
            }
        }
        </script>
        """
        
        context= {'data':output}
        return render(request, 'MunicipalityScreen.html', context)

def DeleteOfficer(request):
    if request.method == 'GET':
        mname = request.session.get('mname')
        if mname is None:
            return render(request, 'MunicipalityLogin.html', {'data': 'Please login first'})
        username = request.GET.get('user', False)
        if not username:
            return render(request, 'MunicipalityScreen.html', {'data': '<div class="status-banner error">Invalid Request</div>'})
            
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("delete from fieldofficer where username='"+username+"'")
            con.commit()
            
        return redirect('ViewOfficer')

def UpdateOfficer(request):
    if request.method == 'GET':
        username = request.GET.get('user', False)
        con = pymysql.connect(**DB_CONFIG)
        data = None
        with con:
            cur = con.cursor()
            cur.execute("select * from fieldofficer where username='"+username+"'")
            data = cur.fetchone()
        return render(request, 'UpdateOfficer.html', {'data': data})

def UpdateOfficerAction(request):
    if request.method == 'POST':
        mname = request.session.get('mname')
        if mname is None:
            return render(request, 'MunicipalityLogin.html', {'data': 'Please login first'})
        
        username = request.POST.get('t1', False)
        password = request.POST.get('t2', False)
        contact = request.POST.get('t3', False)
        
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute(f"update fieldofficer set password='{password}', contact_no='{contact}' where username='{username}'")
            con.commit()
            
        return redirect('ViewOfficer')

def ViewCitizens(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
        output = '<div class="table-container fade-in"><table class="data-table"><thead><tr>'
        output += '<th>Citizen Name</th><th>Contact No</th><th>Email ID</th><th>Address</th><th>Actions</th></tr></thead><tbody>'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select * from signup")
            rows = cur.fetchall()
            for row in rows:
                output += f'<tr><td>{row[0]}</td><td>{row[2]}</td><td>{row[3]}</td><td>{row[4]}</td>'
                output += f'<td><a href="UpdateCitizen?user={row[0]}" style="display:inline-block; background:linear-gradient(135deg, #00b09b 0%, #96c93d 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; margin-right:10px; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-edit"></i></a>'
                output += f'<a href="javascript:void(0);" onclick="confirmDeleteCitizen(\'{row[0]}\')" style="display:inline-block; background:linear-gradient(135deg, #ef476f 0%, #d63654 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-trash"></i></a></td></tr>'
        output += "</tbody></table></div>"
        
        # Add JavaScript for delete confirmation
        output += """
        <script>
        function confirmDeleteCitizen(username) {
            if (confirm('Are you sure you want to delete this citizen? All associated records will be affected.')) {
                window.location.href = 'DeleteCitizen?user=' + username;
            }
        }
        </script>
        """
        context= {'data':output}
        return render(request, 'AdminScreen.html', context)

def DeleteCitizen(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
        username = request.GET.get('user', False)
        if not username:
             return render(request, 'AdminScreen.html', {'data': '<div class="status-banner error">Invalid Request</div>'})
        
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("delete from signup where username='"+username+"'")
            con.commit()
            
        return redirect('ViewCitizens')

def UpdateCitizen(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
        username = request.GET.get('user', False)
        con = pymysql.connect(**DB_CONFIG)
        data = None
        with con:
            cur = con.cursor()
            cur.execute("select * from signup where username='"+username+"'")
            data = cur.fetchone()
        return render(request, 'UpdateCitizen.html', {'data': data})

def UpdateCitizenAction(request):
    if request.method == 'POST':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
            
        username = request.POST.get('t1', False)
        password = request.POST.get('t2', False)
        contact = request.POST.get('t3', False)
        email = request.POST.get('t4', False)
        address = request.POST.get('t5', False)
        
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            sql = f"update signup set password='{password}', contact_no='{contact}', email_id='{email}', address='{address}' where username='{username}'"
            cur.execute(sql)
            con.commit()
            
        # Return to citizen list with success message
        status = '<div class="status-banner success slide-in">Citizen details updated successfully.</div>'
        output = status + '<div class="table-container fade-in"><table class="data-table"><thead><tr>'
        output += '<th>Citizen Name</th><th>Contact No</th><th>Email ID</th><th>Address</th><th>Actions</th></tr></thead><tbody>'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select * from signup")
            rows = cur.fetchall()
            for row in rows:
                output += f'<tr><td>{row[0]}</td><td>{row[2]}</td><td>{row[3]}</td><td>{row[4]}</td>'
                output += f'<td><a href="UpdateCitizen?user={row[0]}" style="display:inline-block; background:linear-gradient(135deg, #00b09b 0%, #96c93d 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; margin-right:10px; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-edit"></i></a>'
                output += f'<a href="javascript:void(0);" onclick="confirmDeleteCitizen(\'{row[0]}\')" style="display:inline-block; background:linear-gradient(135deg, #ef476f 0%, #d63654 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-trash"></i></a></td></tr>'
        output += "</tbody></table></div>"
        
        # Add JavaScript for delete confirmation
        output += """
        <script>
        function confirmDeleteCitizen(username) {
            if (confirm('Are you sure you want to delete this citizen? All associated records will be affected.')) {
                window.location.href = 'DeleteCitizen?user=' + username;
            }
        }
        </script>
        """
        return render(request, 'AdminScreen.html', {'data': output})

def ViewUserComplaint(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
        output = '<div class="table-container fade-in"><table class="data-table"><thead><tr>'
        output += '<th>ID</th><th>Citizen</th><th>Description</th><th>Category</th>'
        output += '<th>Location</th><th>Date</th><th>Municipality</th>'
        output += '<th>Priority</th><th>Severity</th><th>Cost</th><th>Evidence</th>'
        output += '<th>Officer</th><th>Status</th><th>Actions</th></tr></thead><tbody>'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select * from complaint")
            rows = cur.fetchall()
            for row in rows:
                output += f'<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td>'
                output += f'<td><small>{row[4]},<br/>{row[5]}</small></td><td>{row[6]}</td><td>{row[7]}</td>'
                output += f'<td>{row[8]}</td><td>{row[9]}</td><td>{row[10]}</td>'
                output += f'<td><img src="/static/photo/{row[11]}" style="width:80px;height:80px;object-fit:cover;border-radius:8px;"/></td>'
                output += f'<td>{row[12]}</td><td><span class="badge info">{row[13]}</span></td>'
                output += f'<td><a href="UpdateComplaint?cid={row[0]}" style="display:inline-block; background:linear-gradient(135deg, #00b09b 0%, #96c93d 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; margin-right:10px; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-edit"></i></a>'
                output += f'<a href="javascript:void(0);" onclick="confirmDelete({row[0]})" style="display:inline-block; background:linear-gradient(135deg, #ef476f 0%, #d63654 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-trash"></i></a></td></tr>'
        output += "</tbody></table></div>"
        
        # Add JavaScript for delete confirmation
        output += """
        <script>
        function confirmDelete(complaintId) {
            if (confirm('Are you sure you want to delete this complaint? This action cannot be undone.')) {
                window.location.href = 'DeleteComplaint?cid=' + complaintId;
            }
        }
        </script>
        """
        
        context= {'data':output}
        return render(request, 'AdminScreen.html', context)

def ViewMunicipality(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
        output = '<div class="table-container fade-in"><table class="data-table"><thead><tr>'
        output += '<th>Name</th><th>Employee</th><th>Contact No</th><th>Email ID</th><th>Address</th><th>Actions</th></tr></thead><tbody>'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select municipality_name, employee_name, municipality_contact_no, employee_contact_no, city_name from municipality") # Adjusted query based on new headers
            rows = cur.fetchall()
            for row in rows:
                output += f'<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td><td>{row[4]}</td>'
                output += f'<td><a href="UpdateMunicipality?mname={row[0]}" style="display:inline-block; background:linear-gradient(135deg, #00b09b 0%, #96c93d 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; margin-right:10px; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-edit"></i></a>'
                output += f'<a href="javascript:void(0);" onclick="confirmDeleteMunicipality(\'{row[0]}\')" style="display:inline-block; background:linear-gradient(135deg, #ef476f 0%, #d63654 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-trash"></i></a></td></tr>'
        output += "</tbody></table></div>"
        
        # Add JavaScript for delete confirmation
        output += """
        <script>
        function confirmDeleteMunicipality(mname) {
            if (confirm('Are you sure you want to delete this municipality? All associated officers will also be affected.')) {
                window.location.href = 'DeleteMunicipality?mname=' + mname;
            }
        }
        </script>
        """
        
        context= {'data':output}
        return render(request, 'AdminScreen.html', context)

def DeleteMunicipality(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
            
        mname = request.GET.get('mname', False)
        if not mname:
            return render(request, 'AdminScreen.html', {'data': '<div class="status-banner error">Invalid Request</div>'})
            
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("delete from municipality where municipality_name='"+mname+"'")
            con.commit()
            
        return redirect('ViewMunicipality')

def AddMunicipalityAction(request):
    if request.method == 'POST':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
            
        municipality = request.POST.get('t1', False)
        city = request.POST.get('t2', False)
        ename = request.POST.get('emp', False)
        dept_contact = request.POST.get('t3', False)
        emp_contact = request.POST.get('t4', False)
        user = request.POST.get('t5', False)
        password = request.POST.get('t6', False)
        desc = request.POST.get('t7', False) 
        status = 'none'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute(f"select username from municipality where username = '{user}'")
            if cur.fetchone():
                status = 'Given Username already exists'
            else:
                cur.execute(f"insert into municipality values('{municipality}','{city}','{ename}','{dept_contact}','{emp_contact}','{user}','{password}','{desc}')")
                con.commit()
                status = '<div class="status-banner success slide-in">Municipality department successfully established.</div>'
        context= {'data':status}
        return render(request, 'AddMunicipality.html', context)

def UpdateMunicipality(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
        mname = request.GET.get('mname', False)
        con = pymysql.connect(**DB_CONFIG)
        data = None
        with con:
            cur = con.cursor()
            cur.execute("select * from municipality where municipality_name='"+mname+"'")
            data = cur.fetchone()
        return render(request, 'UpdateMunicipality.html', {'data': data})

def UpdateMunicipalityAction(request):
    if request.method == 'POST':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
            
        mname = request.POST.get('t1', False) # Readonly
        city = request.POST.get('t2', False)
        ename = request.POST.get('emp', False)
        dept_contact = request.POST.get('t3', False)
        emp_contact = request.POST.get('t4', False)
        password = request.POST.get('t6', False)
        desc = request.POST.get('t7', False)
        
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            sql = "update municipality set city_name='"+city+"', employee_name='"+ename+"', municipality_contact_no='"+dept_contact+"', employee_contact_no='"+emp_contact+"', password='"+password+"', municipality_desc='"+desc+"' where municipality_name='"+mname+"'"
            cur.execute(sql)
            con.commit()
            
        # Generate view with success message
        status = '<div class="status-banner success slide-in">Municipality details updated successfully.</div>'
        status += '<div class="table-container fade-in"><table class="data-table"><thead><tr>'
        status += '<th>Municipality</th><th>City</th><th>Employee</th><th>Dept Contact</th>'
        status += '<th>Emp Contact</th><th>Username</th><th>Description</th><th>Actions</th></tr></thead><tbody>'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select * from municipality")
            rows = cur.fetchall()
            for row in rows:
                status += f'<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td>'
                status += f'<td>{row[4]}</td><td>{row[5]}</td><td>{row[7]}</td>'
                status += f'<td><a href="UpdateMunicipality?mname={row[0]}" style="display:inline-block; background:linear-gradient(135deg, #00b09b 0%, #96c93d 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; margin-right:20px; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-edit"></i></a>'
                status += f'<a href="javascript:void(0);" onclick="confirmDeleteMunicipality(\'{row[0]}\')" style="display:inline-block; background:linear-gradient(135deg, #ef476f 0%, #d63654 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-trash"></i></a></td></tr>'
        status += "</tbody></table></div>"
        
        # Add JavaScript for delete confirmation
        status += """
        <script>
        function confirmDeleteMunicipality(mname) {
            if (confirm('Are you sure you want to delete this municipality? All associated officers will also be affected.')) {
                window.location.href = 'DeleteMunicipality?mname=' + mname;
            }
        }
        </script>
        """
        return render(request, 'AdminScreen.html', {'data': status})
    
    return ViewMunicipality(request)

def AddMunicipality(request):
    if request.method == 'GET':
        return render(request, 'AddMunicipality.html', {})

def OfficerLoginAction(request):
    if request.method == 'POST':
        option = 0
        username = request.POST.get('t1', False)
        password = request.POST.get('t2', False)
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select username, password, municipality_name FROM fieldofficer")
            rows = cur.fetchall()
            for row in rows:
                if row[0] == username and row[1] == password:
                    request.session['oname'] = username
                    option = 1
                    break
        if option == 1:
            context= {'data':'welcome '+username}
            return render(request, 'OfficerScreen.html', context)
        else:
            context= {'data':'Invalid login details'}
            return render(request, 'OfficerLogin.html', context)

def MunicipalityLoginAction(request):
    if request.method == 'POST':
        option = 0
        username = request.POST.get('t1', False)
        password = request.POST.get('t2', False)
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select username, password, municipality_name, city_name FROM municipality")
            rows = cur.fetchall()
            for row in rows:
                if row[0] == username and row[1] == password:
                    request.session['mname'] = row[2] # Store Department Name for filtering
                    option = 1
                    break
        if option == 1:
            context= {'data':'welcome '+username}
            return render(request, 'MunicipalityScreen.html', context)
        else:
            context= {'data':'Invalid login details'}
            return render(request, 'MunicipalityLogin.html', context)

def OfficerLogin(request):
    if request.method == 'GET':
        return render(request, 'OfficerLogin.html', {})
    
def MunicipalityLogin(request):
    if request.method == 'GET':
        return render(request, 'MunicipalityLogin.html', {})

def AdminLoginAction(request):
    if request.method == 'POST':
        username = request.POST.get('t1', False)
        password = request.POST.get('t2', False)
        if username == 'admin' and password == 'admin':
            request.session['uname'] = 'admin'
            context= {'data':'welcome '+username}
            return render(request, 'AdminScreen.html', context)
        else:
            context= {'data':'Invalid login details'}
            return render(request, 'AdminLogin.html', context)

def AdminLogin(request):
    if request.method == 'GET':
        return render(request, 'AdminLogin.html', {})

def UserLogin(request):
    if request.method == 'GET':
        return render(request, 'UserLogin.html', {})

def index(request):
    # Flush session on logout/entry
    try:
        request.session.flush()
    except:
        pass
    return render(request, 'index.html', {})

def Register(request):
    if request.method == 'GET':
       return render(request, 'Register.html', {})

def RegisterAction(request):
    if request.method == 'POST':
        username = request.POST.get('t1', False)
        password = request.POST.get('t2', False)
        contact = request.POST.get('t3', False)
        email = request.POST.get('t4', False)
        address = request.POST.get('t5', False)        
        if not email.endswith("@gmail.com"):
            status = 'Email must end with @gmail.com'
        else:
            status = 'none'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select username from signup where username = '"+username+"'")
            rows = cur.fetchall()
            for row in rows:
                if row[0] == email:
                    status = 'Given Username already exists'
                    break
        if status == 'none':
            db_connection = pymysql.connect(**DB_CONFIG)
            db_cursor = db_connection.cursor()
            student_sql_query = "INSERT INTO signup(username,password,contact_no,email_id,address) VALUES('"+username+"','"+password+"','"+contact+"','"+email+"','"+address+"')"
            db_cursor.execute(student_sql_query)
            db_connection.commit()
            print(db_cursor.rowcount, "Record Inserted")
            if db_cursor.rowcount == 1:
                status = '<div class="status-banner success slide-in">Account created successfully! You can now login for city services.</div>'
        context= {'data':status}
        return render(request, 'Register.html', context)

def UserLoginAction(request):
    if request.method == 'POST':
        option = 0
        username = request.POST.get('t1', False)
        password = request.POST.get('t2', False)
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select * FROM signup")
            rows = cur.fetchall()
            for row in rows:
                if row[0] == username and row[1] == password:
                    request.session['uname'] = username
                    option = 1
                    break
        if option == 1:
            context= {'data':'welcome '+username}
            return render(request, 'UserScreen.html', context)
        else:
            context= {'data':'Invalid login details'}
            return render(request, 'UserLogin.html', context)

def UpdateComplaint(request):
    if request.method == 'GET':
        cid = request.GET.get('cid', False)
        description = ""
        category = ""
        priority = ""
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute(f"select description, category, priority, status from complaint where complaint_id='{cid}'")
            row = cur.fetchone()
            if row:
                description = row[0]
                category = row[1]
                priority = row[2]
                status = row[3]
        context = {
            'cid': cid,
            'description': description,
            'cat_road': category == "Road Damage",
            'cat_sanitation': category == "Sanitation",
            'cat_water': category == "Drinking Water",
            'cat_garbage': category == "Garbage",
            'cat_other': category == "Other",
            'prio_high': priority == "High",
            'prio_medium': priority == "Medium",
            'prio_low': priority == "Low",
            'stat_pending': status == "Pending",
            'stat_progress': status == "In Progress",
            'stat_resolved': status == "Resolved",
        }
        return render(request, 'UpdateComplaint_final.html', context)

def UpdateComplaintAction(request):
    if request.method == 'POST':
        cid = request.POST.get('cid', False)
        description = request.POST.get('t1', False)
        category = request.POST.get('t2', False)
        priority = request.POST.get('t3', False)
        status = request.POST.get('t4', False)
        
        db_connection = pymysql.connect(**DB_CONFIG)
        db_cursor = db_connection.cursor()
        sql = f"update complaint set description='{description}', category='{category}', priority='{priority}', status='{status}' where complaint_id='{cid}'"
        db_cursor.execute(sql)
        db_connection.commit()
        
        # Send Notification Email using helper
        _send_complaint_update_email(cid, f"SmartCity: Complaint #{cid} Updated by Administrator", "An administrator has updated the details (description, category, or priority) of your grievance.")
        
        # Regenerate ViewUserComplaint with success message
        status_msg = f'<div class="status-banner success slide-in">Complaint #<strong>{cid}</strong> updated successfully.</div>'
        
        output = status_msg + '<div class="table-container fade-in"><table class="data-table"><thead><tr>'
        output += '<th>ID</th><th>Citizen</th><th>Description</th><th>Category</th>'
        output += '<th>Location</th><th>Date</th><th>Municipality</th>'
        output += '<th>Priority</th><th>Severity</th><th>Cost</th><th>Evidence</th>'
        output += '<th>Officer</th><th>Status</th><th>Actions</th></tr></thead><tbody>'
        con = pymysql.connect(**DB_CONFIG)
        with con:
            cur = con.cursor()
            cur.execute("select * from complaint")
            rows = cur.fetchall()
            for row in rows:
                output += f'<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td>'
                output += f'<td><small>{row[4]},<br/>{row[5]}</small></td><td>{row[6]}</td><td>{row[7]}</td>'
                output += f'<td>{row[8]}</td><td>{row[9]}</td><td>{row[10]}</td>'
                output += f'<td><img src="/static/photo/{row[11]}" style="width:80px;height:80px;object-fit:cover;border-radius:8px;"/></td>'
                output += f'<td>{row[12]}</td><td><span class="badge info">{row[13]}</span></td>'
                output += f'<td><a href="UpdateComplaint?cid={row[0]}" style="display:inline-block; background:linear-gradient(135deg, #00b09b 0%, #96c93d 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; margin-right:10px; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-edit"></i></a>'
                output += f'<a href="javascript:void(0);" onclick="confirmDelete({row[0]})" style="display:inline-block; background:linear-gradient(135deg, #ef476f 0%, #d63654 100%); color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600; box-shadow: 0 4px 6px rgba(0,0,0,0.1);"><i class="fas fa-trash"></i></a></td></tr>'
        output += "</tbody></table></div>"
        
        # Add JavaScript for delete confirmation
        output += """
        <script>
        function confirmDelete(complaintId) {
            if (confirm('Are you sure you want to delete this complaint? This action cannot be undone.')) {
                window.location.href = 'DeleteComplaint?cid=' + complaintId;
            }
        }
        </script>
        """
        return render(request, 'AdminScreen.html', {'data': output})

def Broadcast(request):
    if request.method == 'GET':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
        return render(request, 'Broadcast.html', {})

def BroadcastAction(request):
    if request.method == 'POST':
        uname = request.session.get('uname')
        if uname != 'admin':
            return render(request, 'AdminLogin.html', {'data': 'Please login first'})
            
        subject = request.POST.get('t1', False)
        message_body = request.POST.get('t2', False)
        
        con = pymysql.connect(**DB_CONFIG)
        emails = []
        with con:
            cur = con.cursor()
            cur.execute("select email_id from signup")
            rows = cur.fetchall()
            for row in rows:
                if row[0]:
                    emails.append(row[0])
        
        if emails:
            full_message = f"OFFICIAL SMARTCITY BROADCAST\n===========================\n\n{message_body}\n\n---\nBroadcasted by Administrator on {date.today()}"
            try:
                send_mail(subject, full_message, settings.EMAIL_HOST_USER, emails, fail_silently=False)
                status = f"✅ Broadcast sent successfully to {len(emails)} citizens."
            except Exception as e:
                status = f"❌ Error sending broadcast: {str(e)}"
        else:
            status = "⚠️ No registered citizens found to broadcast to."
            
        return render(request, 'Broadcast.html', {'data': status})

