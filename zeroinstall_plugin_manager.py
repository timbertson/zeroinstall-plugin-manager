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
		result = False if boolean else []
		while True:
			try:
				index = relevant_args.index(flag)
			except ValueError:
				return result
			relevant_args.pop(index)
			if boolean:
				return True
			else:
				result.append(relevant_args.pop(index))
	
	if extract_args('--plugin-help', boolean=True):
		print >> sys.stderr, """Options to zeroinstall-plugin-manager are:
	--plugin-add URI       Add a plugin by URI
	--plugin-remove URI    Remove a plugin by URI
	--plugin-list          List current plugins
	--plugin-opt OPT       Pass OPT through to the 0launch
	                       command (e.g '--gui')
	--plugin-command CMD   Run CMD command instead of '""" + Config.default_command + """'
	                       (can be specified multiple times)
	--plugin-help          You're reading it!"""
		return 1

	assert len(relevant_args) > 0, "please specify a main feed URI"
	feed_uri = relevant_args.pop(0)
	config = Config(feed_uri)
	list(map(config.add, extract_args('--plugin-add')))
	list(map(config.remove, extract_args('--plugin-remove')))
	list(map(config.set_name, extract_args('--plugin-manager-name')))
	list(map(config.set_command, extract_args('--plugin-command')))
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
	config.launch_feed(launcher_args=launcher_args, program_args=relevant_args + passthru_args)

class Config(object):
	default_command = 'core'
	def __init__(self, uri):
		self.uri = uri
		self.feed_dirname = urllib.quote(self.uri, safe='').replace(os.path.sep, '_')
		self.config_dir = os.path.join(BaseDirectory.xdg_data_home, 'zeroinstall-plugin-manager', self.feed_dirname)
		self.config_path = os.path.join(self.config_dir, 'uri-list')
		self.name = uri.rstrip('/').rsplit('/',1)[-1]
		self.command = self.default_command
		self._uris = None
		self._lines = None
		self.modified = False

	def get_config_file(self, mode='r'):
		try:
			return open(self.config_path, mode)
		except IOError:
			try:
				os.makedirs(self.config_dir)
			except OSError: pass
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
			'''.format(name=self.name, command=self.command, user=username, runner_uri=self.uri, dependencies=requirement_elems))
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
