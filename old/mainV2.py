import datetime
import logging
import os
import secrets
import string
import hashlib

import mock
from flask import Flask, session, render_template, request, redirect, url_for, send_from_directory
from google.cloud import firestore
import google.auth.credentials

try:
  import googleclouddebugger
  googleclouddebugger.enable(
    breakpoint_enable_canary=True
  )
except ImportError:
  pass


app = Flask(__name__)
#create a key
app.secret_key = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for i in range(8))


if os.getenv('GAE_ENV', '').startswith('standard'):
    # production
    db = firestore.Client()
else:
    # localhost
    os.environ["FIRESTORE_DATASET"] = "test"
    os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8001"
    os.environ["FIRESTORE_EMULATOR_HOST_PATH"] = "localhost:8001/firestore"
    os.environ["FIRESTORE_HOST"] = "http://localhost:8001"
    os.environ["FIRESTORE_PROJECT_ID"] = "test"

    credentials = mock.Mock(spec=google.auth.credentials.Credentials)
    db = firestore.Client(project="test2", credentials=credentials)

def clear_db(db, search_str):
    #Get a new write batch
    batch = db.batch()

    if search_str != '':
        db_ref = db.collection(u'messages').where(u'name', u'==', search_str)
    else:
        db_ref = db.collection(u'messages')

    #Delete all or name's preexisting messages (documents)
    for doc in db_ref.get():
        batch.delete(doc.reference)

    batch.commit()

def form_resub_chk():
    result = True
    # encoding form data using encode()
    # then sending to md5()
    str2hash = request.form.get("name").strip() + request.form.get("message").strip()
    hashedformdata =hashlib.md5(str2hash.encode()).hexdigest()
    # logging.warning(hashedformdata)
    if 'form_data_hash' in session:
        if hashedformdata == session['form_data_hash']:
            result = False
            #logging.warning('here1!!')
        else:
            session['form_data_hash'] = hashedformdata
            #logging.warning('here2!!')
    else:
        #logging.warning('here3!!')
        session['form_data_hash'] = hashedformdata
    #logging.warning(session['form_data_hash'])
    return result
def get_query_data():
    sort_types = ['created','name','message']
    try:
        sort_by = request.args.get('sort_by')
        if sort_by not in sort_types:
            sort_by = 'created'
        search_str = request.args.get('search_str','')
        sort_direction = request.args.get('sort_direction')
        if sort_direction != 'ASCENDING' and sort_direction != 'DESCENDING':
            sort_direction = 'ASCENDING'
        return tuple((sort_by,search_str,sort_direction))
    except:
        return tuple(('created','','ASCENDING'))

def fix_firestore_names(sort_by):
    sort_type = u'created'
    if sort_by == 'message':
        sort_type = u'message'
    elif sort_by == 'name':
        sort_type = u'name'
    return sort_type

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route("/new_entry.html", methods=["GET", "POST"])
def new_entry():
    if (request.method == "POST"):
        messages_ref = db.collection(u'messages')
        if (request.form.get("message") is not None):
            #Check for resubmission
            if form_resub_chk():
                # add message to Firestore
                message_ref = messages_ref.document()  # create a message document reference
                # now you can create or update the message document (set: if it exists, update it. If not, create a new one).
                message_ref.set({
                    u'name': u'{}'.format(request.form.get("name").strip().title()),
                    u'message': u'{}'.format(request.form.get("message").strip().capitalize()),
                    u'created': datetime.datetime.now(),
                    })
        return redirect(url_for('index', sort_by=request.form.get("sort_by"), search_str=request.form.get("search_str"),sort_direction=request.form.get("sort_direction")))
    else:
        sort_by,search_str,sort_direction = get_query_data()
        return render_template("new_entry.html", sort_by=sort_by, search_str=search_str,sort_direction=sort_direction)

@app.route("/", methods=["GET", "POST"])
def index():
    #Default values
    sort_type = u'created'
    sort_by = 'created'
    sort_direction = 'ASCENDING'
    search_str = ''
    # a reference to the messages collection
    messages_ref = db.collection(u'messages')
    if (request.method == "POST"):
        if (request.form.get("sort_by") is not None):
            sort_by = request.form.get("sort_by")
            if sort_by == 'created':
                sort_type = u'created'
            elif sort_by == 'message':
                sort_type = u'message'
            else: sort_type = u'name'

        if (request.form.get("sort_direction") is not None):
            sort_direction = request.form.get("sort_direction")

        search_str = request.form.get("search_str")

        if (request.form.get("formType") == 'utils'):
            if (request.form.get("sort_by_select") == 'message'):
                sort_by = 'message'
            elif (request.form.get("sort_by_select") == 'name'):
                sort_by = 'name'
            sort_type = fix_firestore_names(sort_by)

            if (request.form.get("delete_data") is not None):
                clear_db(db, search_str)
    else:
        sort_by,search_str,sort_direction = get_query_data()
        sort_type = fix_firestore_names(sort_by)
    #logging.warning(sort_direction + ' ' + sort_type)
    # get all messages from the Firestore
    if search_str != '':
        if sort_by == 'name':
            #Avoid order by clause cannot contain a field with an equality filter name
            #Coz the search is from the name field!!
            messages_gen = messages_ref.where(u'name', u'==', search_str).stream()
        else:
            #Setup search for documents
            messages_gen = messages_ref.where(u'name', u'==', search_str).order_by(sort_type, direction=sort_direction).stream()
    else:
        #Get all message documents
        messages_gen = messages_ref.order_by(sort_type, direction=sort_direction).stream()
        #direction=firestore.Query.DESCENDING
    # messages generator: holds all message documents (these documents need to be converted to dicts)
    messages = []
    for message in messages_gen:
        message_dict = message.to_dict()  # converting DocumentSnapshot into a dictionary

        message_dict["id"] = message.id  # adding message ID to the dict, because it's not there by default
        messages.append(message_dict)  # appending the message dict to the messages list

        # logging.warning(type(message))  # Type is DocumentSnapshot (google/cloud/firestore_v1/document.py)
        #logging.warning(message.get("message"))  # this is how you get data from DocumentSnapshot

        # interesting in-built time features
        # logging.warning(message.read_time)
        #logging.warning(message.create_time)
        # logging.warning(message.update_time)

    mes_flag = False
    if len(messages) != 0: mes_flag = True
    return render_template("index.html", messages=messages, mess_flag=mes_flag, sort_by=sort_by, search_str=search_str,sort_direction=sort_direction)


@app.route("/basic", methods=["GET"])
def basic():
    return "Basic handler without HTML template"


if __name__ == '__main__':
    if os.getenv('GAE_ENV', '').startswith('standard'):
        app.debug = True
        app.run()  # production
    else:
        app.run(port=8080, host="localhost", debug=True)  # localhost
