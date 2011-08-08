#!/usr/bin/env python

import sys, os
import cgi
import getpass
import urllib
from xdg import BaseDirectory
import itertools

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

	
	if extract_args('--plugin-help', boolean=True):
		print >> sys.stderr, """Options to zeroinstall-plugin-manager are:
	--plugin-add URI       Add a plugin by URI
	--plugin-remove URI    Remove a plugin by URI
	--plugin-list          List current plugins
	--plugin-opt OPT       Pass OPT through to the 0launch
	                       command (e.g '--gui')
	--plugin-command CMD   Run CMD command instead of '""" + Config.default_command + """'
	                       (can be specified multiple times)
	--plugin-exec-uri URI  Launch URI instead of the main feed
	--plugin-help          You're reading it!"""
		return 1

	assert len(relevant_args) > 0, "please specify a main feed URI"
	feed_uri = relevant_args.pop(0)
	config = Config(feed_uri)
	list(map(config.add, extract_args('--plugin-add')))
	list(map(config.remove, extract_args('--plugin-remove')))
	list(map(config.set_name, extract_args('--plugin-manager-name')))
	list(map(config.set_command, extract_args('--plugin-command')))
	list(map(config.set_exec_uri, extract_args('--plugin-exec-uri')))
	launcher_args = extract_args('--plugin-opt')
	def print_uris():
		print "\n".join(sorted(config.uris))

	if(config.modified):
		config.save()
		print >> sys.stderr, "Updated plugin list for %s:" % (config.uri,)
		print_uris()
		return
	if extract_args('--plugin-list', boolean=True):
		print_uris()
		return
	unknown_args = list(arg for arg in relevant_args if arg.startswith('--plugin-'))
	if unknown_args:
		print >> sys.stderr, "Unknown plugin-manager arg: %s (use -- to ignore following options)" % (unknown_args,)
		return False
	config.launch_feed(launcher_args=launcher_args, program_args=relevant_args + passthru_args)

class Config(object):
	default_command = 'core'
	def __init__(self, uri):
		self.uri = uri
		self.execute_uri = uri
		self.feed_dirname = urllib.quote(self.uri, safe='').replace(os.path.sep, '_')
		self.config_dir = os.path.join(BaseDirectory.xdg_data_home, 'zeroinstall-plugin-manager', self.feed_dirname)
		self.config_path = os.path.join(self.config_dir, 'uri-list')
		self.name = uri.rstrip('/').rsplit('/',1)[-1]
		self.command = self.default_command
		self._uris = None
		self._lines = None
		self.modified = False
	
	def set_exec_uri(self, uri):
		self.execute_uri = uri

	def ensure_directory(self):
		if not os.path.exists(self.config_dir):
			os.makedirs(self.config_dir)

	def get_config_file(self, mode='r'):
		self.ensure_directory()
		try:
			return open(self.config_path, mode)
		except IOError:
			open(self.config_path, 'w').close()
			return open(self.config_path, mode)

	@property
	def lines(self):
		if self._lines is None:
			with self.get_config_file() as f:
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

	def launch_feed(self, program_args, launcher_args=[]):
		feed_path = self.write_feed()
		os.execvp('0launch', ['0launch'] + launcher_args + [feed_path] + program_args)

	def write_feed(self):
		self.ensure_directory()
		with open(self.feed_path, 'w') as output_feed:
			username = getpass.getuser()
			def requirement(uri):
				return '<requires interface=\"%s\"/>' % (cgi.escape(uri),)

			requirement_elems = "\n".join(map(requirement, self.uris))
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
		with self.get_config_file('w') as out:
			print >> out, "\n".join(uris)
			if comments:
				print >> out, "\n".join(comments)
		self.modified = False

	def add(self, uri):
		self.uris.add(uri)
		self.modified = True
	
	def remove(self, uri):
		try:
			self.uris.remove(uri)
		except KeyError: pass
		self.modified = True

if __name__ == '__main__':
	sys.exit(main())
