# PiTiVi , Non-linear video editor
#
#       ui/publishtoyoutubedialog.py
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
Dialog for publishing to Web
"""

import gtk
import time
import thread
import os
from gst import SECOND
from pitivi.log.loggable import Loggable
from pitivi.actioner import Renderer
from pitivi import configure
from pitivi.uploader import YTUploader, DMUploader, VimeoUploader
from gettext import gettext as _
from gobject import timeout_add
from string import ascii_lowercase, ascii_uppercase, maketrans, translate
from pitivi.utils import beautify_length
try :
    import gnomekeyring as gk
    unsecure_storing = False
except :
    unsecure_storing = True
import pycurl

catlist = []

dailymotion_cat = ['News', 'Shortfilms', 'Music', 'Sport', 'Tech', 'Travel', 'Auto', 'Creation', 'Webcam', 'People', 'Lifestyle', 'Fun', 'Videogames', 'Animals', 'School']

youtube_cat = ['Film', 'Autos', 'Music', 'Animals', 'Sports', 'Travel', 'Games', 'Comedy', 'People', 'News', 'Entertainment', 'Education', 'Howto', 'Nonprofit', 'Tech']

class PublishToWebDialog(Renderer):

    def __init__(self, app, project, pipeline=None):
        Loggable.__init__(self)
        self.app_settings = app.settings

        self.app = app
        self.pipeline = pipeline
        self.project = project

        self.builder = gtk.Builder()
        self.builder.add_from_file(os.path.join(configure.get_ui_dir(),
            "publishtoweb.ui"))
        self._setProperties()
        self.builder.connect_signals(self)

        # UI widgets
        self.oldsettings = self.app.project.getSettings()
        self.settings = self.oldsettings.copy()
        self.settings.setEncoders(muxer='mp4mux', vencoder='xvidenc', aencoder="lamemp3enc")
        self.app.project.setSettings(self.settings)
        self.app.publish_button.set_sensitive(False)

        #Auto-completion
        if unsecure_storing :
            self.builder.get_object("checkbutton1").set_label("Remember me ! Warning : \
storage will not be secure. Install python-gnomekeyring.")
            if self.app_settings.login:
                self.username.set_text(self.app_settings.login)
                self.password.set_text(self.app_settings.password)
        elif "pitivi" in gk.list_keyring_names_sync():
            item_keys = gk.list_item_ids_sync('pitivi')
            gk.unlock_sync('pitivi', 'gkpass')
            item_info = gk.item_get_info_sync('pitivi', item_keys[0])
            if item_info :
                self.username.set_text(item_info.get_display_name())
                self.password.set_text(item_info.get_secret())
            gk.lock_sync('pitivi')

        self.uploader = YTUploader()
        self.categories = gtk.combo_box_new_text()
        self.builder.get_object("table2").attach(self.categories, 1, 2, 3, 4)


        self.uploadbar = gtk.ProgressBar()
        self.stopbutton = gtk.ToolButton(gtk.STOCK_CANCEL)
        self.hbox = gtk.HBox()
        self.hbox.pack_start(self.uploadbar)
        self.hbox.pack_end(self.stopbutton)
        self.taglist = []

        self.updateFilename(self.project.name)
        self.filebutton = gtk.FileChooserButton("Select a file")
        self.builder.get_object("table2").attach(self.filebutton, 1, 2, 5, 6)
        self.filebutton.set_action(gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
        self.filebutton.set_current_folder(self.app.settings.lastExportFolder)
        self.filebutton.show()

        self.remember_me = False

        # Assistant pages
        self.service_page = self.window.get_nth_page(0)
        self.login_page = self.window.get_nth_page(1)
        self.verifier_page = self.window.get_nth_page(2)
        self.metadata_page = self.window.get_nth_page(3)
        self.render_page = self.window.get_nth_page(4)
        self.announce_page = self.window.get_nth_page(5)

        self.categories.connect("changed", self._categoryChangedCb)
        self.stopbutton.connect('clicked', self._finishCb)
        self.mainquitsignal = self.app.connect('destroy', self._mainQuitCb)
        self.connect("eos", self._renderingDoneCb)
        self.window.connect("delete-event", self._deleteEventCb)

        self.metadata = {
            "title": "",
            "description": "",
            "private": False,
            "category": None,
            "tags": "",
        }
        self.has_started_rendering = False
        self.window.set_forward_page_func(self.page_func)

    def page_func(self, current_page):
        if current_page == 0 and self.uploader.auth_type == "verifier":
            return 2
        else:
            return current_page + 1


    def _setProperties(self):
        self.window = self.builder.get_object("publish-assistant")
        self.description = self.builder.get_object("description")
        self.tags = self.builder.get_object("tags")

        self.login = self.builder.get_object("login")
        self.login_status = self.builder.get_object("login_status")
        self.username = self.builder.get_object("username")
        self.password = self.builder.get_object("password")
        self.verifier = self.builder.get_object("verifier_code")
        self.verifier_url = self.builder.get_object("verifier_url")

        self.renderbar = self.builder.get_object("renderbar")
        self.fileentry = self.builder.get_object("fileentry")

    def updateFilename(self, name):
        self.fileentry.set_text(name + ".mp4")

    def _storePassword(self):
        if unsecure_storing:
            self.app_settings.login = self.username.get_text()
            self.app_settings.password = self.password.get_text()
            self.app_settings.storeSettings()
        else :
            if "pitivi" not in gk.list_keyring_names_sync():
                gk.create_sync('pitivi', 'gkpass')
            atts = {'username':'pitivi',
                    'server':'Youtube',
                    'service':'HTTP',
                    'port':'80',
                   }
            a = gk.item_create_sync('pitivi', gk.ITEM_GENERIC_SECRET,
                self.username.get_text(), atts, self.password.get_text(), True)

    def _update_metadata_page_complete(self):
        is_complete = all([
            len(self.metadata["title"]) != 0,
            len(self.metadata["description"]) != 0,
        ])

        self.window.set_page_complete(self.metadata_page, is_complete)

    def _startRendering(self):

        self.has_started_rendering = True

        # Start rendering:
        self.filename = self.filebutton.get_uri() + "/" + self.fileentry.get_text()
        Renderer.__init__(self, self.project, self.pipeline, outfile =
                self.filename)
        self.app.set_sensitive(False)
        self.startAction()
        self.renderbar.set_fraction(0)
        self.visible = True

    def updatePosition(self, fraction, estimated, uploading = False):
        if not uploading:
            self.renderbar.set_fraction(fraction)
            self.app.set_title(_("%d%% Rendered") % int(100 * fraction))
        else:
            self.uploadbar.set_fraction(fraction)
        if estimated and not uploading:
            self.renderbar.set_text(_("About %s left in rendering") % estimated)
        elif estimated and uploading:
            self.uploadbar.set_text(_("About %s left in uploading") % estimated)

    def _shutDown(self):
        self.debug("shutting down")
        if self.uploader.uploader:
            self.uploader.uploader.run = False
        self.app.project.setSettings(self.oldsettings)
        self.app.set_sensitive(True)
        self.app.publish_button.set_sensitive(True)
        self.app.handler_disconnect(self.mainquitsignal)

        # Abort recording
        if self.has_started_rendering:
            self.removeAction()
        self.window.destroy()

    def _rememberMeCb(self, button):
        self.remember_me = False
        if button.get_active():
            self.remember_me = True

    def _authorizeVerifierCb(self, *args):
        self.uploader.authenticate_with_verifier(self.verifier.get_text(), self._verifierResultCb)
        self.window.set_page_complete(self.verifier_page, True)


    def _verifierResultCb(self, result):
        if result == 'good':
            self.window.set_page_complete(self.verifier_page, True)


    def _loginClickedCb(self, *args):
        self.debug("login clicked")
        self.login_status.set_text("Logging in...")
        # TODO: This should activate a throbber
        thread.start_new_thread (self.uploader.authenticate_with_password, (self.username.get_text(),
            self.password.get_text(), self._loginResultCb))

    def _loginResultCb(self, result):
        # TODO: The throbber should now be deactivated
        if result == 'good':
            if self.remember_me:
                self._storePassword()
            self.window.set_page_complete(self.login_page, True)
            self.window.set_current_page(self.window.get_current_page() + 2)
        else:
            status, exception = result
            self.login_status.set_text('Unable to login')
            self.window.set_page_complete(_verifierChangedCb_verifierChangedCbself.login_page, False)

    def _titleChangedCb(self, entry):
        self.metadata["title"] = entry.get_text()
        self._update_metadata_page_complete()

    def _descriptionChangedCb(self, entry):
        self.metadata["description"] = entry.get_text()
        self._update_metadata_page_complete()

    def _tagsChangedCb(self, entry):
        self.metadata["tags"] = entry.get_text()

    def _videoServiceChangedCb(self, combo):
        if combo.get_active_text() == "YouTube":
            catlist = youtube_cat
            self.uploader = YTUploader()

        elif combo.get_active_text() == "Daily Motion":
            catlist = dailymotion_cat
            self.uploader = DMUploader()

        else:
            self.uploader = VimeoUploader()
            catlist= []
            self.verifier_url.set_label(self.uploader.get_oauth_url())
            self.verifier_url.set_uri(self.uploader.get_oauth_url())

        self.categories.show()
        self.categories.set_title("Choose a category")
        for e in catlist:
            self.categories.append_text(e)
        self.window.set_page_complete(self.service_page, True)

    def _categoryChangedCb(self, combo):
        self.metadata["category"] = combo.get_active_text()

    def _changeStatusCb (self, button):
        if button.get_active():
            self.metadata["private"] = True
        else:
            self.metadata["private"] = False

    def _prepareCb(self, assistant, page):
        if page == self.render_page and not self.has_started_rendering:
            self._startRendering()

    def _renderingDoneCb(self, data):
        self.app.set_sensitive(True)
        self.app.set_title(_("PiTiVi"))
        self.timestarted = time.time()
        self.window.hide()
        self.app.sourcelist.pack_end(self.hbox, False, False)
        self.hbox.show_all()
        self.filename = self.filename.split("://")[1]
        self.uploader.upload(self.filename, self.metadata, self._uploadProgressCb, self._uploadDoneCb)

    def _uploadProgressCb(self, done, total):
        timediff = time.time() - self.timestarted
        fraction = float(min(done, total)) / float(total)
        if timediff > 3.0:
            totaltime = (timediff * float(total) / float(done)) - timediff
            text = beautify_length(int(totaltime * SECOND))
            self.updatePosition(fraction, text, uploading = True)

    def _uploadDoneCb(self, video_entry):
        self.entry = gtk.Entry()
        try:
            link = video_entry.find_html_link().split("&")[0]
        except:
            link = video_entry
        self.entry.set_text(link)
        self.uploadbar.destroy()
        self.hbox.pack_start (self.entry)
        self.entry.show()

    def _mainQuitCb(self, ignored):
        self.window.destroy()

    def _deleteEventCb(self, window, event):
        self.debug("delete event")
        self._shutDown()

    def _cancelCb(self, ignored):
        self.debug("cancel event")
        self._shutDown()

    def _destroyCb (self, ignored):
        self._shutDown()

    def _finishCb(self, unused):
        self.hbox.destroy()
        self._shutDown()
