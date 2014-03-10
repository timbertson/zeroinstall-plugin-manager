#!/usr/bin/env python
from __future__ import print_function, unicode_literals

import sys, os
import cgi
import getpass
import subprocess
import shutil
#from xdg import BaseDirectory # not available in py3; we don't need much of it. See `_get_config_dir`
import itertools

if sys.version_info > (3,):
	import urllib.parse
	url_unquote = urllib.parse.unquote
	url_quote = urllib.parse.quote
else:
	import urllib
	url_unquote = urllib.unquote
	url_quote = urllib.quote

def main():
	args = sys.argv[1:]

	not_double_dash = lambda x: x != '--'
	relevant_args = list(itertools.takewhile(not_double_dash, args))
	passthru_args = list(itertools.dropwhile(not_double_dash, args))

	def extract_args(flag, boolean=False):
		if boolean:
			def find_and_remove_next_bool():
				try:
					index = relevant_args.index(flag)
				except ValueError:
					return None
				relevant_args.pop(index)
				return True
			return len(list(iter(find_and_remove_next_bool, None))) > 0

		else:
			def find_and_remove_next_value():
				for index, arg in enumerate(relevant_args):
					if arg == flag:
						relevant_args.pop(index)
						return relevant_args.pop(index)
					elif arg.startswith(flag + '='):
						relevant_args.pop(index)
						return arg.split('=', 1)[1]
				else:
					return None
			return list(iter(find_and_remove_next_value, None))

	
	store = Store()

	if extract_args('--plugin-use-system-zeroinstall', boolean=True):
		print("WARN: --plugin-use-system-zeroinstall is deprecated", file=sys.stderr)

	if len(relevant_args) == 0:
		known_uris = "\n".join(sorted(store.uris))
		print("Please specify a main feed URI.\nKnown URIs in %s:\n\n%s" % (store.base, known_uris), file=sys.stderr)
		return 0
	if extract_args('--plugin-help', boolean=True) or relevant_args[0] in ("--help", "-h"):
		print("""Usage: zeroinstall-plugin-manager FEED_URI [plugin-options] [--] [program-arguments]
  program-args will be passed through to the called program.
  plugin-options are:

  --plugin-with URI      Run with URI (for just this session)
  --plugin-without URI   Run without URI (for just this session)
  --plugin-add URI       Add a plugin by URI
  --plugin-remove URI    Remove a plugin by URI
  --plugin-list          List current plugins
  --plugin-edit          Edit plugins (via $EDITOR)
  --plugin-reset         Remove all plugin config for this URI
  --plugin-opt OPT       Pass OPT through to the 0install
                         command (e.g '--gui')
  --plugin-command CMD   Run CMD command instead of '""" + Config.default_command + """'
                         (can be specified multiple times)
  --plugin-exec-uri URI  Launch URI instead of the main feed
                         (i.e launch this uri with main URI's plugins)
  --plugin-help          You're reading it!

Call with no arguments to see a list of URIs where plugins have been used.""", file=sys.stderr)
		return 1
	feed_uri = relevant_args.pop(0)
	assert "://" in feed_uri and not feed_uri.startswith("-"), "invalid URI: " + feed_uri
	config = store[feed_uri]
	list(map(config.add, extract_args('--plugin-add')))
	list(map(config.remove, extract_args('--plugin-remove')))

	list(map(config.session_add, extract_args('--plugin-with')))
	list(map(config.session_remove, extract_args('--plugin-without')))

	if extract_args('--plugin-edit', boolean=True):
		config.edit()
	if extract_args('--plugin-reset', boolean=True):
		config.erase()
		return 0
	list(map(config.set_name, extract_args('--plugin-manager-name')))
	list(map(config.set_command, extract_args('--plugin-command')))
	list(map(config.set_exec_uri, extract_args('--plugin-exec-uri')))
	launcher_args = extract_args('--plugin-opt')
	def print_uris():
		print("\n".join(sorted(config.uris)))

	if(config.modified):
		config.save()
		print("Updated plugin list for %s:" % (config.uri,), file=sys.stderr)
		print_uris()
		return
	if extract_args('--plugin-list', boolean=True):
		print_uris()
		return
	unknown_args = list(arg for arg in relevant_args if arg.startswith('--plugin-'))
	if unknown_args:
		print("Unknown plugin-manager arg: %s (use -- to ignore following options)" % (unknown_args,), file=sys.stderr)
		return False
	config.launch_feed(launcher_args=launcher_args, program_args=relevant_args + passthru_args, bootstrap = False)

def _get_config_dir(name):
	"""if we already have a dir in $XDG_DATA_HOME, use that for backwards compatibility.
	Otherwise, use the config dir"""
	home = os.path.expanduser('~')
	xdg_data_home = os.environ.get('XDG_DATA_HOME') or os.path.join(home, '.local', 'share')
	data_loc = os.path.join(xdg_data_home, name)
	if os.path.exists(data_loc): return data_loc

	xdg_config_home = os.environ.get('XDG_CONFIG_HOME') or os.path.join(home, '.config')
	return os.path.join(xdg_config_home, name)

class Store(object):
	def __init__(self):
		self.base = os.path.join(_get_config_dir('zeroinstall-plugin-manager'))
	
	@property
	def contents(self):
		return os.listdir(self.base)
	
	@property
	def uris(self):
		return map(url_unquote, self.contents)

	def dir_for(self, uri):
		try:
			result = url_quote(uri, safe='')
		except TypeError as e:
			raise ValueError("Invalid uri: %r\n(Original error: %s)" % (uri, e))
		assert os.path.sep not in result
		return os.path.join(self.base, result)

	def __getitem__(self, uri):
		return Config(store=self, uri=uri)

class Config(object):
	default_command = 'core'
	def __init__(self, store, uri):
		self.uri = uri
		self.execute_uri = uri
		self.config_dir = store.dir_for(uri)
		self.uri_list_file = os.path.join(self.config_dir, 'uri-list')
		self.name = uri.rstrip('/').rsplit('/',1)[-1]
		self.command = self.default_command
		self.session_additions = set()
		self.session_removals = set()
		self._uris = None
		self._lines = None
		self.modified = False

	def set_exec_uri(self, uri):
		self.execute_uri = uri

	@property
	def directory_exists(self):
		return os.path.exists(self.config_dir)

	def ensure_directory(self):
		if not self.directory_exists:
			os.makedirs(self.config_dir)

	def open_uri_list(self, mode='r'):
		self.ensure_directory()
		try:
			return open(self.uri_list_file, mode)
		except IOError:
			open(self.uri_list_file, 'w').close()
			return open(self.uri_list_file, mode)
	
	def ensure_uri_list(self):
		self.open_uri_list().close()

	@property
	def lines(self):
		if self._lines is None:
			with self.open_uri_list() as f:
				self._lines = list(line.strip() for line in f.readlines())
		return self._lines

	@property
	def uris(self):
		if self._uris is None:
			self._uris = set(line for line in self.lines if line and not line.startswith("#"))
			self._initial_uris = self._uris.copy()
		return self._uris

	@property
	def feed_path(self):
		return os.path.join(self.config_dir, 'user-feed.xml')

	def set_name(self, name):
		self.name = name

	def set_command(self, cmd):
		self.command = cmd

	def launch_feed(self, program_args, launcher_args=[], bootstrap=True):
		feed_path = self.write_feed()
		exe = os.environ.get('ZI_BIN', '0install')
		base_args = [exe, 'run']
		if bootstrap:
			base_args = base_args + ['-c', 'http://0install.net/2007/interfaces/ZeroInstall.xml']
		argv = base_args + ['-c'] + launcher_args + [feed_path] + program_args
		os.execvp(exe, argv)

	def write_feed(self):
		self.ensure_directory()
		uris = self.uris
		uris = uris.union(self.session_additions)
		uris = uris.difference(self.session_removals)
		with open(self.feed_path, 'w') as output_feed:
			username = getpass.getuser()
			def requirement(uri):
				return '<requires interface=\"%s\" importance="recommended"/>' % (cgi.escape(uri),)

			requirement_elems = "\n".join(map(requirement, uris))
			output_feed.write('''<?xml version="1.0" ?>
			<?xml-stylesheet type='text/xsl' href='interface.xsl'?>
			<interface xmlns="http://zero-install.sourceforge.net/2004/injector/interface">
				<name>{name}</name>
				<summary>{name} plugin collection for {user}</summary>
				<description>
				</description>

				<group>
					<command name="run">
						<runner interface="{runner_uri}" command="{command}"/>
					</command>
					{dependencies}
					<implementation id="." version="1.0"/>
				</group>
			</interface>\n
			'''.format(name=self.name, command=self.command, user=username, runner_uri=self.execute_uri, dependencies=requirement_elems))
		return self.feed_path

	def save(self):
		uris = self.uris
		existing_uris = self._initial_uris
		existing_lines = set(self.lines)

		comments = existing_lines.difference(existing_uris)
		with self.open_uri_list('w') as out:
			print("\n".join(uris), file=out)
			if comments:
				print("\n".join(comments), file=out)
		self.modified = False

	def add(self, uri):
		self.uris.add(uri)
		self.modified = True
	
	def remove(self, uri):
		try:
			self.uris.remove(uri)
		except KeyError: pass
		self.modified = True
	
	def session_add(self, uri):
		self.session_additions.add(uri)

	def session_remove(self, uri):
		self.session_removals.add(uri)
	
	def edit(self):
		editor = os.environ.get('EDITOR', 'vi')
		self.ensure_uri_list()
		print("launching editor... for %s" % (self.uri_list_file,), file=sys.stderr)
		edit = subprocess.Popen([editor, self.uri_list_file])
		edit.wait()
		print()
		self.modified = True
	
	def erase(self):
		if self.directory_exists:
			shutil.rmtree(self.config_dir)
		print("removed all plugin settings for %s" % (self.uri,))
		self.modified = True

if __name__ == '__main__':
	sys.exit(main())
