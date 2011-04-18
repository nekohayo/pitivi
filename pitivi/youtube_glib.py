# PiTiVi , Non-linear video editor
#
#       youtube_glib.py
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
