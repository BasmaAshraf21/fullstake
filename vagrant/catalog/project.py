from flask import Flask, render_template, 
requestrequest, redirect, url_for, flash, jsonify
# import CRUD operations
from database_setup import Base, Restaurant, MenuItem, User
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from flask import session as login_session
import random, string


from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json

from flask import make_response
import requests

app = Flask(__name__)



CLIENT_ID = json.loads(
    open('client_secrets.json' , 'r').read())['web']['client_id']
APPLICATION_NAME = "MenuRestaurant"


engine = create_engine('sqlite:///restaurantmenuwithusers.db', 
																							connect_args={'check_same_thread': False})
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()


# create state token to prevent request forgery.
# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in range(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    return render_template('login.html', STATE=state)

# login with google account

@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print ("Token's client ID does not match app's.")
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(
									json.dumps('Current user is already connected.'),200)
                                 
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # see if user exists, if it doesn't make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px;'\
              'height: 300px;'\
              'border-radius: 150px;'\
              '-webkit-border-radius: 150px;'\
              '-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output


# User Helper Functions


def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


    # DISCONNECT - Revoke a current user's token and reset their login_session

# logout from google account
@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session.get('access_token')
    if access_token is None:
        print ('Access Token is None')
        response = make_response(
									json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    print ('In gdisconnect access token is %s', access_token)
    print ('User name is: ')
    print login_session['username']
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' 
				% login_session['access_token']
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print ('result is ')
    print result
    if result['status'] == '200':
        # Reset the user's sesson.
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        # For whatever reason, the given token was invalid.
        response = make_response(
									json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response

@app.route("/")
@app.route("/restaurants/")

def restaurant():
    restaurant = session.query(Restaurant).all()
    return render_template('index.html', restaurant= restaurant)

 # Show all restaurant 
@app.route("/allrestaurants")

def ShowRestaurants():
    restaurant = session.query(Restaurant).all()
    if 'username' not in login_session:
        return render_template('publicrestaurants.html', restaurant = restaurant)
    else:
        return render_template('restaurants.html', restaurant = restaurant)

 # Show menu of restaurant
@app.route("/restaurants/<int:restaurant_id>/")

def restaurantMenu(restaurant_id):
    restaurant = session.query(Restaurant)
		.filter_by(id = restaurant_id).one_or_none()
    creator = getUserInfo(restaurant.user_id)
    items = session.query(MenuItem).filter_by(restaurant_id = restaurant.id)
    if 'username' not in login_session or creator.id != login_session['user_id']:
        return render_template('publicmenu.html', items=items, 
																															restaurant = restaurant, creator=creator)
    else:
        return render_template('menu.html', items=items, 
																															restaurant = restaurant, creator=creator)


 # Create new restaurant
	
@app.route('/restaurants/new/', methods=['GET', 'POST'])

def newRestaurant():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newrestaurant = Restaurant(name = request.form['name'], 
																																			user_id = login_session['user_id'])
        session.add(newrestaurant)
        session.commit()
        session.close()
        flash("New Restaurant created!")
        return redirect(url_for('ShowRestaurants'))
    else:
        return render_template('newrestaurant.html')

 # Edit restaurant
	
@app.route('/restaurants/<int:restaurant_id>/edit/', methods=['GET', 'POST'])

def editRestaurant(restaurant_id):
    if 'username' not in login_session:
        return redirect('/login')
    editedRestaurant = session.query(Restaurant)
				.filter_by(id = restaurant_id).one_or_none()
    if editedRestaurant.user_id != login_session['user_id']:
        return "<script>function myFunction()"\
               "{alert('You are not authorized to edit this restaurant."\
               "Please create your own restaurant in order to edit.');}"\
               "</script><body onload='myFunction()'>"
    if request.method == 'POST':
        if request.form['name']:
            editedRestaurant.name = request.form['name']
        flash('Restaurant Successfully Edited %s' % editedRestaurant.name)
        return redirect(url_for('ShowRestaurants'))
    else:
        return render_template('editrestaurant.html', i = editedRestaurant)

    
 # Delete restaurant
	
@app.route('/restaurants/<int:restaurant_id>/delete/', methods =['GET', 'POST'])

def deleteRestaurant(restaurant_id):    
    if 'username' not in login_session:
        return redirect('/login')
    restaurantToDelete = session.query(Restaurant).filter_by(id = restaurant_id).one_or_none()
    if restaurantToDelete.user_id != login_session['user_id']:
        return "<script>function myFunction()"\
               "{alert('You are not authorized to delete this restaurant."\
               "Please create your own restaurant in order to delete.');}"\
               "</script><body onload='myFunction()'>"
    if request.method == 'POST':
        session.delete(restaurantToDelete)
        session.commit()
        flash(" menu item has been deleted!")
        return redirect(url_for('ShowRestaurants', restaurant_id = restaurant_id))
    else:
        return render_template('deleterestaurant.html', i = restaurantToDelete)

    
 # Create new menu item
@app.route('/restaurants/<int:restaurant_id>/new/', methods = ['GET', 'POST']) 

def newMenuItem(restaurant_id):
    if 'username' not in login_session:
      return redirect('/login')
    new = session.query(Restaurant).filter_by(id = restaurant_id).one_or_none()
    if login_session['user_id'] != new.user_id:
        return "<script>function myFunction()"\
               "{alert('You are not authorized to add menu items to this restaurant."\
               "Please create your own restaurant in order to add items.');}"\
               "</script><body onload='myFunction()'>"
    if request.method == 'POST':
        newItem = MenuItem(name = request.form['name'],description = request.form['description'],
                           priceprice = request.form['price'], 
																											restaurant_id = restaurant_id, user_id=new.user_id)

        session.add(newItem)
        session.commit()
        session.close()
        flash("new menu item created!")
        return redirect(url_for('restaurantMenu', restaurant_id = restaurant_id))
    else:
        return render_template('newmenuitem.html', restaurant_id = restaurant_id, i= new)

 # Edit menu item
@app.route('/restaurants/<int:restaurant_id>/<int:menu_id>/edit/', methods=['GET','POST'])
def editMenuItem(restaurant_id, menu_id):
    if 'username' not in login_session:
      return redirect('/login')
    editedItem = session.query(MenuItem).filter_by(id = menu_id).one_or_none()
    if login_session['user_id'] != editedItem.user_id:
        return "<script>function myFunction()"\
               "{alert('You are not authorized to edit menu items to this restaurant."\
               "Please create your own restaurant in order to edit items.');}"\
               "</script><body onload='myFunction()'>"
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        session.add(editedItem)
        session.commit()
        session.close()
        flash(" Menu Item has been edited!")
        return redirect(url_for('restaurantMenu', restaurant_id = restaurant_id))
    else:
        return render_template('editmenuitem.html', restaurant_id = restaurant_id, menu_id = menu_id, i= editedItem)
    
 # Delete menu item
@app.route('/restaurants/<int:restaurant_id>/<int:menu_id>/delete/', methods=['GET','POST'])
def deleteMenuItem(restaurant_id, menu_id):
    if 'username' not in login_session:
      return redirect('/login')
    itemToDelete = session.query(MenuItem).filter_by(id = menu_id).one_or_none()
    if login_session['user_id'] != itemToDelete.user_id:
        return "<script>function myFunction()"\
               "{alert('You are not authorized to delete menu items to this restaurant."\
               "Please create your own restaurant in order to delete items.');}"\
               "</script><body onload='myFunction()'>"
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        session.close()
        flash(" Menu Item has been deleted!")
        return redirect(url_for('restaurantMenu', restaurant_id = restaurant_id))
    else:
        return render_template('deletemenuitem.html', i = itemToDelete)
        

    
  #making an API Endpoint (Get Request)
@app.route('/restaurants/<int:restaurant_id>/menu/JSON')   
def restaurantMenuJSON(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id = restaurant_id).one()
    items = session.query(MenuItem).filter_by(restaurant_id = restaurant_id ).all()
    return jsonify(MenuItems = [i.serialize for i in items])


  #Add yourAPI Endpoint Here
@app.route('/restaurants/<int:restaurant_id>/menu/<int:menu_id>/JSON')   
def menuItemJSON(restaurant_id, menu_id):
    menuItem = session.query(MenuItem).filter_by(id = menu_id).one()
    return jsonify(MenuItem = menuItem.serialize)






if __name__ == "__main__":
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host = '0.0.0.0', port = 8080)
