# ZeroInstall Plugin Manager

<img src="http://gfxmonk.net/dist/status/project/zeroinstall-plugin-manager.png">

This program is intended to be used as a `<runner>` for another
zero install feed, e.g:

	<command name="run">
		<runner interface="http://gfxmonk.net/dist/0install/zeroinstall-plugin-manager.xml">
			<arg>http://example.com/your-feed.xml</arg>
		</runner>
	</command>
	<command name="core" path="my-program-executable"/>

It manages a user-specific list of feed URIs ("plugins"), and
launches the desired URL (this *must* be the first argument)
with those URIs as additional dependencies.

By default, zeroinstall-plugin-manager will launch your feed's
`core` command while adding all current plugins as dependencies
(it can't use `run`, as that would cause infinite recursion in
the typical case).

zeroinstall-plugin-manager will consume all options that start
with "--plugin-". If you need to prevent this, it will stop at
the first argument equal to "--".

	Options to zeroinstall-plugin-manager are:
		--plugin-add URI       Add a plugin by URI
		--plugin-remove URI    Remove a plugin by URI
		--plugin-list          List current plugins
		--plugin-opt OPT       Pass OPT through to the 0launch
		                       command (e.g '--gui')
		--plugin-command CMD   Run CMD command instead of 'core'
		                       (can be specified multiple times)
		--plugin-help          You're reading it!

If you don't like those options, feel free to simply depend upon
this feed, then import `zeroinstall_plugin_manager.Config`
yourself and have at it.

