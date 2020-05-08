#!/usr/bin/python

# Copyright: (c) 2020, Florian Bergmann <Bergmann.F@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

ANSIBLE_METADATA = {
    'metadata_version': '0.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: toml_file

short_description: This module allows modifying TOML files.

extends_documentation_fragment:
    - files

version_added: "2.10"

description:
    - "This is my longer description explaining my test module"

options:
  path:
    description:
        - Path to a TOML-file; Thie file is created if required.
    type: path
    required: true
  section:
    description:
      - Section name in TOML file. This is added if C(state=present) automatically when
          a single value is being set.
      - If left empty or set to C(null), the I(option) will be placed before the first I(section).
      - Using C(null) is also required if the config format does not support sections.
    type: str
    required: true
  key:
    description:
      - If set (required for changing a I(value)), this is the name of the key.
    type: str
  value:
    description:
      - The string value to be associated with an I(option).
      - May be omitted when removing an I(option).
    type: str
  state:
    description:
      - If set to C(absent) the option or section will be removed if present instead of created.
    type: str
    choices: [ absent, present ]
    default: present
  create:
    description:
      - If set to C(no), the module will fail if the file does not already exist.
      - By default it will create the file if it is missing.
    type: str
    default: yes

author:
    - Florian Bergmann (@bergmannf)
'''

EXAMPLES = '''
# Pass in a message
- name: Ensure "fav=lemonade is in section "[drinks]" in specified file
  toml_file:
    path: /etc/conf.toml
    section: drinks
    option: fav
    value: lemonade
    mode: '0600'
'''

RETURN = '''
original_message:
    description: The original name param that was passed in
    type: str
    returned: always
message:
    description: The output message that the test module generates
    type: str
    returned: always
'''

# EXAMPLE TOML:
toml_string = """
# This is a TOML document.

title = "TOML Example"

[owner]
name = "Tom Preston-Werner"
dob = 1979-05-27T07:32:00-08:00 # First class dates

[database]
server = "192.168.1.1"
ports = [ 8001, 8001, 8002 ]
connection_max = 5000
enabled = true

[[servers]]

  # Indentation (tabs and/or spaces) is allowed but not required
  [servers.alpha]
  ip = "10.0.0.1"
  dc = "eqdc10"

  [servers.beta]
  ip = "10.0.0.2"
  dc = "eqdc10"

[clients]
data = [ ["gamma", "delta"], [1, 2] ]

# Line breaks are OK when inside arrays
hosts = [
  "alpha",
  "omega"
]
"""

import os
import toml
import tempfile
import traceback

from ansible.module_utils.basic import AnsibleModule

def do_toml(module: AnsibleModule, path: str, section: str, key: str, value: str, state: str, create: str) -> dict:
    changed = False
    diff = dict(before='', after='')
    msg = []
    working_context = None
    if os.path.exists(path):
        try:
            content = toml.load(path)
        except toml.TomlDecodeError as e:
            msg.append("Could not decode file at {} as TOML".format(path))
            module.fail_json(msg=msg, traceback=traceback.format_exc())
    else:
        content = toml.loads("")

    # Find the right section to work on.
    if section:
        if state == "present":
            if section not in content:
                content[section] = dict()
                working_context = content[section]
                changed = True
                msg.append("Added section {}.".format(section))
            else:
                working_context = content[section]
        if state == "absent":
            if key:
                if section in content:
                    working_context = content[section]
            elif section in content:
                content.pop(section)
                changed = True
                msg.append("Removed section {}.".format(section))
    else:
        working_context = content

    # Add or remove the key in the working_context (either global or the section to work in)
    # TODO: Do we have to split the key?
    if key:
        if state == 'present':
            if key not in working_context:
                working_context[key] = None
            if working_context[key] != value:
                working_context[key] = value
                changed = True
                msg.append("Added key {}={}.".format(key, value))
        elif state == 'absent':
            if key in working_context:
                if not value:
                    working_context.pop(key)
                    changed = True
                    msg.append("Removed key {}.".format(key))
                elif working_context[key] == value:
                    working_context.pop(key)
                    changed = True
                    msg.append("Removed key {}.".format(key))

    if changed and not module.check_mode:
        try:
            tmpfd, tmpfile = tempfile.mkstemp(dir=module.tmpdir)
            f = os.fdopen(tmpfd, 'w')
            toml.dump(content, f)
            f.close()
        except IOError:
            module.fail_json(msg="Unable to create temporary file %s", traceback=traceback.format_exc())

        try:
            module.atomic_move(tmpfile, path)
        except IOError:
            module.ansible.fail_json(
                msg='Unable to move temporary file %s to %s, IOError' % (tmpfile, path), traceback=traceback.format_exc()
            )
    print("Changed: {}", changed)
    return dict(changed=changed, origin_message=diff, msg=' '.join(msg))

def run_module():

    result = dict(
        changed=False,
        original_message='',
        message=''
    )

    module = AnsibleModule(
        argument_spec=dict(
            path=dict(type='str', required=True),
            section=dict(type='str'),
            key=dict(type='str'),
            value=dict(type='str'),
            state=dict(type='str', default="present", choices=['absent', 'present']),
            create=dict(type='bool', default=True),
        ),
        add_file_common_args=True,
        supports_check_mode=True
    )

    path = module.params['path']
    section = module.params['section']
    key = module.params['key']
    value = module.params['value']
    state = module.params['state']
    create = module.params['create']

    if module.check_mode:
        module.exit_json(**result)

    result = do_toml(module, path, section, key, value, state, create)

    if not module.check_mode and os.path.exists(path):
        file_args = module.load_file_common_arguments(module.params)
        changed = module.set_fs_attributes_if_different(file_args, result['changed'])

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)

def main():
    run_module()

if __name__ == '__main__':
    main()

