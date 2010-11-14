# PiTiVi , Non-linear video editor
#
#       youtube_glib.py
#
# Copyright (c) 2010, Magnus Hoff <maghoff@gmail.com>
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
import gdata.youtube, gdata.youtube.service
import threading
from Queue import Queue


CLIENT_ID = 'PiTiVi'
DEVELOPER_KEY = 'AI39si5DzhNX8NS0iEZl2Xg3uYj54QG57atp6v5w-FDikhMRYseN6MOtR8Bfvss4C0rTSqyJaTvgN8MHAszepFXz-zg4Zg3XNQ'

class PipeWrapper:
    """Helper class to make gdata work with pipes"""
    def __init__(self, f):
        self._f = f
    def read(self, *args):
        return self._f.read(*args)


def upload(yt_service, metadata, filename):
    my_media_group = gdata.media.Group(
        title = gdata.media.Title(text=metadata["title"]),
        description = gdata.media.Description(description_type='plain', text=metadata["description"]),
        category = [
            gdata.media.Category(
                text = 'Autos',
                scheme = 'http://gdata.youtube.com/schemas/2007/categories.cat',
                label = 'Autos',
            ),
        ],
        private = gdata.media.Private() if metadata["private"] else None,
    )
    video_entry = gdata.youtube.YouTubeVideoEntry(
        media = my_media_group,
    )
    new_entry = yt_service.InsertVideoEntry(video_entry, filename)
    return new_entry


class YTThread(threading.Thread):
    def __init__(self, queue):
        threading.Thread.__init__(self)
        self._queue = queue

    def run(self):
        self._yt_service = gdata.youtube.service.YouTubeService()
        self._yt_service.source = CLIENT_ID
        self._yt_service.developer_key = DEVELOPER_KEY
        self._yt_service.client_id = CLIENT_ID

        self._running = True
        while self._running:
            task = self._queue.get()
            task()

    def yt_stop(self):
        self._running = False

    def authenticate_with_password(self, username, password, callback):
        try:
            self._yt_service.email = username
            self._yt_service.password = password
            self._yt_service.ProgrammaticLogin()
            gobject.idle_add(callback, ("good", self._yt_service.GetClientLoginToken()))
        except Exception, e:
            gobject.idle_add(callback, ("bad", e))

    def authenticate_with_token(self, token, callback):
        self._yt_service.SetClientLoginToken(token)
        gobject.idle_add(callback, token)

    def upload(self, filename, metadata, callback):
        try:
            new_entry = upload(self._yt_service, metadata, filename())
            gobject.idle_add(callback, ("good", new_entry))
        except Exception, e:
            gobject.idle_add(callback, ("bad", e))


class AsyncYT:
    def __init__(self):
        self._queue = Queue()
        self._yt_thread = YTThread(self._queue)
        self._yt_thread.start()

    def __del__(self):
        """This is an absolute last resort. Please call stop() manually instead"""
        self.stop()

    def authenticate_with_password(self, username, password, callback):
        self._queue.put(lambda: self._yt_thread.authenticate_with_password(username, password, callback))

    def authenticate_with_token(self, token, callback):
        self._queue.put(lambda: self._yt_thread.authenticate_with_token(token, callback))

    def upload(self, filename, metadata, callback):
        self._queue.put(lambda: self._yt_thread.upload(filename, metadata, callback))

    def stop(self):
        self._queue.put(self._yt_thread.yt_stop)
        self._yt_thread.join()
