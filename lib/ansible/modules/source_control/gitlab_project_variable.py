#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2019, Markus Bergholz (markuman@gmail.com)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = '''
module: gitlab_project_variable
short_description: Creates/updates/deletes Gitlab Projects Variables
description:
  - When a project variable does not exists, it will be created.
  - When a project variable does exists, its value will be updated when the values are different.
  - Variables which are presented in the playbook, but are not presented in the Gitlab project,
    they stay untouched (purged_vars = False) or will be deleted (purged_vars = True).
version_added: "2.9"
author:
    - "Markus Bergholz (@markuman)"
requirements:
  - python >= 2.7
  - python-gitlab python module
extends_documentation_fragment:
  - auth_basic
options:
  state:
    description:
      - create or delete project variable.
      - Possible values are present and absent.
    default: present
    type: str
    choices: ["present", "absent"]
  project:
    description:
      - The path and name of the project
    required: true
    type: str
  purge:
    description:
      - When set to true, all variables which are not presented in the task will be deleted.
    default: false
    required: false
    type: bool
  vars:
    description:
      - A list of key value pairs
    default: {}
    required: false
    type: dict
'''


EXAMPLES = '''
- name: Set or update some CI/CD variables
  gitlab_project_variable:
    api_url: https://gitlab.com
    api_token: secret_access_token
    project: markuman/dotfiles
    purge: False
    vars:
      ACCESS_KEY_ID: abc123
      SECRET_ACCESS_KEY: 321cba

- name: delete one variable
  gitlab_project_variable:
    api_url: https://gitlab.com
    api_token: secret_access_token
    project: markuman/dotfiles
    state: absent
    vars:
      ACCESS_KEY_ID: abc123
'''

RETURN = '''
msg:
  description: Success or failure message
  returned: always
  type: str
  sample: "Success"

result:
  description: json parsed response from the server
  returned: always
  type: dict

error:
  description: the error message returned by the Gitlab API
  returned: failed
  type: str
  sample: "Failed to connect to Gitlab server: 401: 401 Unauthorized"

project_variable:
  description: three lists of the variablenames which were added, updated or removed.
  returned: always
  type: dict
'''

import traceback

from ansible.module_utils.basic import AnsibleModule, missing_required_lib
from ansible.module_utils._text import to_native
from ansible.module_utils.api import basic_auth_argument_spec


GITLAB_IMP_ERR = None
try:
    import gitlab
    HAS_GITLAB_PACKAGE = True
except Exception:
    GITLAB_IMP_ERR = traceback.format_exc()
    HAS_GITLAB_PACKAGE = False


class gitlab_project_variables(object):

    def __init__(self, module):
        self.repo = gitlab.Gitlab(module.params['api_url'],
                                  private_token=module.params['api_token'])
        self.project = self.get_project(module.params['project'])
        self._module = module

    def auth(self):
        self.repo.auth()

    def get_project(self, project_name):
        return self.repo.projects.get(project_name)

    def list_all_project_variables(self):
        raw_variable_list = self.project.variables.list()
        retval = []
        if len(raw_variable_list) > 0:
            for item in raw_variable_list:
                retval.append(item.get_id())
        return retval

    def create_variable(self, key, value):
        if self._module.check_mode:
            return
        return self.project.variables.create({"key": key, "value": value})

    def update_variable(self, key, value):
        var = self.project.variables.get(key)
        if var.value == value:
            return False
        if self._module.check_mode:
            return True
        var.save()
        return True

    def delete_variable(self, key):
        if self._module.check_mode:
            return
        return self.project.variables.delete(key)


def native_python_main(this_gitlab, purge, var_list, state):

    change = False
    return_value = dict(added=list(), updated=list(), removed=list())

    existing_variables = this_gitlab.list_all_project_variables()

    for key in var_list:
        if key in existing_variables and state == 'present':
            change = this_gitlab.update_variable(
                key, var_list[key]) or change
            pop_index = existing_variables.index(key)
            existing_variables.pop(pop_index)
            return_value['updated'].append(key)
        elif key not in existing_variables and state == 'present':
            this_gitlab.create_variable(key, var_list[key])
            change = True
            return_value['added'].append(key)
        elif key in existing_variables and state == 'absent':
            this_gitlab.delete_variable(key)
            change = True
            return_value['removed'].append(key)

    if len(existing_variables) > 0 and purge:
        for item in existing_variables:
            this_gitlab.delete_variable(item)
            change = True
            return_value['removed'].append(item)

    existing_variables = this_gitlab.list_all_project_variables()
    return change, return_value


def main():
    argument_spec = basic_auth_argument_spec()
    argument_spec.update(
        api_token=dict(required=True, no_log=True, type='str'),
        project=dict(required=True, type='str'),
        purge=dict(required=False, default=False, type='bool'),
        vars=dict(required=False, default=dict(), type='dict'),
        state=dict(type='str', default="present", choices=["absent", "present"])
    )

    module = AnsibleModule(
        argument_spec=argument_spec,
        required_together=[
            ['api_url', 'api_token']
        ],
        supports_check_mode=True
    )

    if not HAS_GITLAB_PACKAGE:
        module.fail_json(msg=missing_required_lib("python-gitlab"), exception=GITLAB_IMP_ERR)

    try:
        this_gitlab = gitlab_project_variables(module=module)
        this_gitlab.auth()
    except (gitlab.exceptions.GitlabAuthenticationError, gitlab.exceptions.GitlabGetError) as e:
        module.fail_json(msg="Failed to connect to Gitlab server: %s" % to_native(e))
    except (gitlab.exceptions.GitlabHttpError) as e:
        module.fail_json(msg="Failed to connect to Gitlab server: %s. \
            Gitlab remove Session API now that private tokens are removed from user API endpoints since version 10.2" % to_native(e))

    purge = module.params['purge']
    var_list = module.params['vars']
    state = module.params['state']

    change, return_value = native_python_main(this_gitlab, purge, var_list, state)

    module.exit_json(changed=change, project_variable=return_value)


if __name__ == '__main__':
    main()
