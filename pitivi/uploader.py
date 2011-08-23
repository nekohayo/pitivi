# PiTiVi , Non-linear video editor
#
#       uploader.py
#
# Copyright (c) 2010, Mathieu Duponchelle <seeed@laposte.net>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

"""
Helpers to communicate asynchronously with YouTube from a GLib program.

The most interesting entrypoint is the AsyncYT class.
"""

import gobject
import gdata.youtube
import gdata.youtube.client
import gdata.client
import gdata.youtube.data
from os.path import getsize

import thread
from httplib2 import Http
from urllib import urlencode
import json
import urllib2
import pycurl

APP_NAME = 'PiTiVi'
DEVELOPER_KEY = 'AI39si5DzhNX8NS0iEZl2Xg3uYj54QG57atp6v5w-FDikhMRYseN6MOtR8Bfvss4C0rTSqyJaTvgN8MHAszepFXz-zg4Zg3XNQ'
CREATE_SESSION_URI = '/resumable/feeds/api/users/default/uploads'

class ResumableYouTubeUploader(object):

    def __init__(self, filepath, client):

        self.client = client
        self.client.host = "uploads.gdata.youtube.com"

        self.f = open(filepath)
        file_size = getsize(self.f.name)

        self.uploader = gdata.client.ResumableUploader(
            self.client, self.f, "video/avi", file_size,
            chunk_size=1024*64, desired_class=gdata.youtube.data.VideoEntry)

    def __del__(self):
        if self.uploader is not None:
            self.uploader.file_handle.close()

    def uploadInManualChunks(self, new_entry, on_chunk_complete, callback):
        uri = CREATE_SESSION_URI
        self.run = True

        self.uploader._InitSession(uri, entry=new_entry, headers={"X-GData-Key": "key=" + DEVELOPER_KEY,
                                                                  "Slug" : None})

        start_byte = 0
        entry = None

        while not entry and self.run:
            entry = self.uploader.UploadChunk(start_byte, self.uploader.file_handle.read(self.uploader.chunk_size))
            start_byte += self.uploader.chunk_size
            on_chunk_complete(start_byte, self.uploader.total_file_size)
        callback(entry)


class UploadBase():
    def __init__(self):
        self.uploader = None

    def authenticate_with_password(self, username, password, callback):
        pass

    def upload(self, filename, metadata, callback):
        pass

class YTUploader(UploadBase):
    def __init__(self):
        UploadBase.__init__(self)
        self.auth_type = 'password'


    def authenticate_with_password(self, username, password, callback):
        try:
            self.client = gdata.youtube.client.YouTubeClient(source=APP_NAME)
            self.client.ssl = False
            self.client.http_client.debug = False
            self.convert = None
            self.client.ClientLogin(username, password, self.client.source)
            gobject.idle_add(callback, ("good"))
        except Exception, e:
            gobject.idle_add(callback, ("bad", e))

    def upload(self, filename, metadata, progressCb, doneCb):
        self.uploader = ResumableYouTubeUploader(filename, self.client)

        text = metadata['category'] if metadata['category'] != None else 'Film'
        print text
        my_media_group = gdata.media.Group(
            keywords = gdata.media.Keywords(text=metadata["tags"]),
            title = gdata.media.Title(text=metadata["title"]),
            description = gdata.media.Description(description_type='plain', text=metadata["description"]),
            category = [
                gdata.media.Category(
                    text = text,
                    scheme = 'http://gdata.youtube.com/schemas/2007/categories.cat',
                ),
            ],
            private = gdata.media.Private() if metadata["private"] else None,
        )
        new_entry = gdata.youtube.YouTubeVideoEntry(media=my_media_group)
        thread.start_new_thread(self.uploader.uploadInManualChunks, (new_entry, progressCb, doneCb))

class DMUploader(UploadBase):
    def __init__(self):
        UploadBase.__init__(self)
        self.BASE = 'https://api.dailymotion.com/json'
        self.KEY = '5650e080523c04177265'
        self.SECRET = '8d0d8e5ee4c16b05dbb34244d221b1c4423e149c'
        self.OAUTH = 'https://api.dailymotion.com/oauth/token'
        self.auth_type = 'password'


    def authenticate_with_password(self, username, password, callback):
        #OAuth2 to fetch access_token and refresh_token 
        values = {'grant_type' : 'password',
                  'client_id' : self.KEY,
                  'client_secret' : self.SECRET,
                  'username' : username,
                  'password' : password,
                  'scope':'write read'
                  }
        data = urlencode(values)
        try:
            req = urllib2.Request(self.OAUTH, data)
            response = urllib2.urlopen(req)
            result = json.load(response)
            self.access_token = result['access_token']
            self.refresh_token = result['refresh_token']
            self.UURL= '?access_token='+self.access_token
            gobject.idle_add(callback, ("good"))
        except Exception, e:
            gobject.idle_add(callback, ("bad", e))

    def upload(self, filepath, metadata, progressCb, doneCb):

        self.filepath = filepath
        self.progressCb = progressCb
        self.doneCb = doneCb
        self.metadata = metadata

        job = json.dumps({"call":"file.upload", "args":None})
        req = urllib2.Request(self.BASE+self.UURL, job, {'content-type':'application/json'})
        response = urllib2.urlopen(req)
        result = json.load(response)
        upload_url= result['result']['upload_url']
        self.uploader = DailyMotionFileUpload(filepath, upload_url)
        thread.start_new_thread(self.uploader.UploadFile, 
                    (self.on_upload_progress, self.on_upload_finish))

    def on_upload_finish(self, response):
        result = json.loads(response)

        job = json.dumps({"call":"video.create","args":{"url":result['url']}})
        req = urllib2.Request(self.BASE+self.UURL, job, {'content-type': 'application/json'})
        responsed = urllib2.urlopen(req)
        result = json.load(responsed)
        id = result['result']['id']

        #publish video
        job=json.dumps({"call":"video.edit", "args":{"id":id, "title":self.metadata['title'],
                    "tags":self.metadata['tags'], "channel":self.metadata['category'],
                    "description":self.metadata['description'], "published":"true", 
                    "private":self.metadata['private']}})
        req = urllib2.Request(self.BASE+self.UURL, job, {'content-type': 'application/json'})
        response = urllib2.urlopen(req)
        video_url = 'http://www.dailymotion.com/video/' + id
        self.doneCb(video_url)

    def on_upload_progress(self, dt, dd, utotal, udone):
        if utotal and udone:
            self.progressCb(udone, utotal)


class DailyMotionFileUpload(object):
    def __init__(self, filepath, upload_url):

        self.upload_url = upload_url
        self.filepath = filepath

    def UploadFile(self,  on_upload_progress, on_upload_finish):
        self.curl = pycurl.Curl()
        self.curl.setopt(pycurl.POST, 1)
        self.curl.setopt(pycurl.URL, str(self.upload_url))
        self.curl.setopt(pycurl.NOPROGRESS, 0)
        self.curl.setopt(self.curl.WRITEFUNCTION, on_upload_finish)
        self.curl.setopt(self.curl.PROGRESSFUNCTION, on_upload_progress)
        self.curl.setopt(self.curl.HTTPPOST, [
          ("file", (self.curl.FORM_FILE, self.filepath))])
        self.curl.perform()
        self.curl.close()

