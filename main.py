#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import os
import hashlib
import time
import logging
import urllib
from datetime import datetime, date, time
from google.appengine.ext import blobstore
from google.appengine.api import memcache
from google.appengine.api import xmpp
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import xmpp_handlers
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.api import channel
from django.utils.html import strip_tags
from django.utils import simplejson  

##
# Adds a user to a room.
def add_to_room(room, user, channel):
  #!!! LOCKING ISSUE. LET'S IGNORE THIS FOR THE SAKE OF THIS SIMPLE APP!!!# 
  #!!! At worst, a user may actually not be in the list of listeners... let's hope he reloads that page in time !!!#
  listeners = []
  try:
    listeners = simplejson.loads(memcache.get(key=room))
  except :
    # Well huh
    listeners = []
    
  listeners.append([channel, user])
  memcache.set(key=room, value=simplejson.dumps(listeners), time=1800)

##
# Sends messages to all members of a room
def send_to_room(room, msg):
  listeners = []
  try:
    listeners = simplejson.loads(memcache.get(key=room))
  except :
    # Well huh
    listeners = []
  
  for listener in listeners:
    logging.info(listener[0]);
    if listener[0] == "http":
      channel.send_message(listener[1], simplejson.dumps(msg))
    elif listener[0] == "xmpp":
      xmpp.send_message(listener[1], msg["name"] + " : " + msg["message"])   


##
# In charge of rendering the home page, and redirect to the right room
class MainHandler(webapp.RequestHandler):
  def render(self, template_file, template_values = {}):
     path = os.path.join(os.path.dirname(__file__), 'templates', template_file)
     self.response.out.write(template.render(path, template_values))
  
  def get(self):
    self.render("index.html")

  def post(self):
    self.redirect("/r/"+self.request.get("room"))


##
# Handles rooms : shows and post messages
class RoomHandler(webapp.RequestHandler):
  def render(self, template_file, template_values = {}):
     path = os.path.join(os.path.dirname(__file__), 'templates', template_file)
     self.response.out.write(template.render(path, template_values))
  
  def get(self, room):
    user  = hashlib.md5(datetime.now().isoformat()).hexdigest()
    add_to_room(room, user, "http")
    token = channel.create_channel(user)
    self.render("room.html", {"room": room, 'token': token})

  def post(self, room):
    # Adds messages to the rooms.
    msg = {"message": strip_tags(self.request.get("message")), "name": strip_tags(self.request.get("name"))};
    send_to_room(room, msg)

##
# File uploader
class UploadHandler(blobstore_handlers.BlobstoreUploadHandler):
  def render(self, template_file, template_values = {}):
     path = os.path.join(os.path.dirname(__file__), 'templates', template_file)
     self.response.out.write(template.render(path, template_values))
  
  def post(self, room):
    upload_files = self.get_uploads('file')  # 'file' is file upload field in the form
    blob_info = upload_files[0]
    send_to_room(self.request.get("room"), {"name": "ChitChat", "message": "<a target='_blank' href='/serve/%s'>File uploaded!</a>"% blob_info.key()})
    self.redirect('/upload/%s?done=success' % self.request.get("room"))

  def get(self, room):
    if self.request.get("done") == "success":
      self.render("done.html")
    else:
      upload_url = blobstore.create_upload_url('/upload/')
      self.render("upload.html", {"room": room, 'upload_url': upload_url})

##
# Uploaded file handler
class ServeHandler(blobstore_handlers.BlobstoreDownloadHandler):
  def get(self, resource):
    resource = str(urllib.unquote(resource))
    blob_info = blobstore.BlobInfo.get(resource)
    self.send_blob(blob_info)

##
# XMPP Handler
class XMPPHandler(xmpp_handlers.CommandHandler):
  def join_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    user = message.sender.rpartition("/")[0]
    room = message.arg
    add_to_room(room, user, "xmpp")
    memcache.set(key=user, value=room, time=1800)
    message.reply("Congrats, you joined the room '" + room + "'");

  def help_command(self, message=None):
    message = xmpp.Message(self.request.POST)
    help_msg = "This is a simple chatroom client which can be used both from the web, or from an XMPP client:\n\n" \
      "/join XYZ -> joins the XYZ room\n\n" \
      "/help ->  get help message\n"
    message.reply(help_msg)
    message.reply(message.body)

  def text_message(self, message=None):
    message = xmpp.Message(self.request.POST)
    user = message.sender.rpartition("/")[0]
    msg = {"message": strip_tags(message.body), "name": user};
    room = memcache.get(key=user)
    send_to_room(room, msg)


def main():
    application = webapp.WSGIApplication([
      ('/_ah/xmpp/message/chat/', XMPPHandler), 
      ('/', MainHandler), 
      ('/r/([^/]+)?', RoomHandler), 
      ('/upload/([^/]+)?', UploadHandler),
      ('/serve/([^/]+)?', ServeHandler)
    ],debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
