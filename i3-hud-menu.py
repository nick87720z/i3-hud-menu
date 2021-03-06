#!/usr/bin/env python3

import dbus
import subprocess

from sys import argv
from getopt import getopt
from os import getenv

max_width = 0

prefix = [''     ,
          ' ' + (b' '                       ).decode('utf-8') + '  ',
          ' ' + (b' \xE2\x83\x9E'           ).decode('utf-8') + '  ',
          ' ' + (b'\xE2\xAC\xA4\xE2\x83\x9E').decode('utf-8') + '  ',
          ' ' + (b' \xE2\x83\x9D'           ).decode('utf-8') + '  ',
          ' ' + (b'\xE2\xAC\xA4\xE2\x83\x9D').decode('utf-8') + '  ' ]

def help():
  print ("Usage:")
  print (" " + argv[0] + " [--dmenu=CMD] [--sep=SEPARATOR] [--markup]")

"""
  format_label_list
"""
def format_label_list(label_list):
  if len(label_list) == 0:
    return ''
  head, *tail = label_list
  result = head
  for label in tail:
    result = result + separator + label
  return result

"""
  try_appmenu_interface
"""
def try_appmenu_interface(window_id):
  # --- Get Appmenu Registrar DBus interface
  session_bus = dbus.SessionBus()
  appmenu_registrar_object = session_bus.get_object('com.canonical.AppMenu.Registrar', '/com/canonical/AppMenu/Registrar')
  appmenu_registrar_object_iface = dbus.Interface(appmenu_registrar_object, 'com.canonical.AppMenu.Registrar')

  # --- Get dbusmenu object path
  try:
    dbusmenu_bus, dbusmenu_object_path = appmenu_registrar_object_iface.GetMenuForWindow(window_id)
  except dbus.exceptions.DBusException:
    return

  # --- Access dbusmenu items
  dbusmenu_object = session_bus.get_object(dbusmenu_bus, dbusmenu_object_path)
  dbusmenu_object_iface = dbus.Interface(dbusmenu_object, 'com.canonical.dbusmenu')
  dbusmenu_items = dbusmenu_object_iface.GetLayout(0, -1, ["label"])

  dbusmenu_item_dict = dict()

  """ explore_dbusmenu_item """
  def explore_dbusmenu_item(item, label_list):
    item_id = item[0]
    item_props = item[1]
    item_children = item[2]

    if 'label' in item_props:
      new_label_list = label_list + [item_props['label']]
    else:
      new_label_list = label_list

    # FIXME: This is not excluding all unactivable menuitems.
    if len(item_children) == 0:
      dbusmenu_item_dict[format_label_list(new_label_list)] = item_id
    else:
      for child in item_children:
        explore_dbusmenu_item(child, new_label_list)

  explore_dbusmenu_item(dbusmenu_items[1], [])

  # --- Run dmenu
  dmenu_string = ''
  head, *tail = dbusmenu_item_dict.keys()
  dmenu_string = head
  for m in tail:
    dmenu_string += '\n'
    dmenu_string += m

  dmenu_cmd = subprocess.Popen(dmenu_exe + ['-p', 'Application Menu'], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
  dmenu_cmd.stdin.write(dmenu_string.encode('utf-8'))
  dmenu_result = dmenu_cmd.communicate()[0].decode('utf-8').strip('\n')
  dmenu_cmd.stdin.close()

  # --- Use dmenu result
  if dmenu_result in dbusmenu_item_dict:
    action = dbusmenu_item_dict[dmenu_result]
    print(dbusmenu_object_iface.Event(action, 'clicked', 0, 0))


"""
  try_gtk_interface
"""
def try_gtk_interface(g_bus_name_cmd, g_menubar_path_cmd, g_action_path_cmd):
  global max_width
  global success

  g_bus_name = g_bus_name_cmd.split(' ')[2].split('\n')[0].split('"')[1]
  print(g_menubar_path_cmd)
  print(g_action_path_cmd)
  g_menubar_path = g_menubar_path_cmd.split(' ')[2].split('\n')[0].split('"')[1]
  g_action_path  = g_action_path_cmd.split(' ')[2].split('\n')[0].split('"')[1]
  print("GTK MenuModel Bus name and object path: ", g_bus_name, g_menubar_path)

  # --- Ask for menus over DBus ---
  session_bus = dbus.SessionBus()
  g_menubar_object = session_bus.get_object(g_bus_name, g_menubar_path)
  g_action_object  = session_bus.get_object(g_bus_name, g_action_path)
  g_menubar_object_iface = dbus.Interface(g_menubar_object, dbus_interface='org.gtk.Menus')
  g_action_object_iface = dbus.Interface(g_action_object, dbus_interface='org.gtk.Actions')
  g_menubar_results = g_menubar_object_iface.Start([x for x in range(1024)])

  if len(g_menubar_results) == 0:
    return

  # --- Construct menu list ---
  g_menubar_menus = dict()
  for g_menubar_result in g_menubar_results:
    g_menubar_menus[(g_menubar_result[0], g_menubar_result[1])] = g_menubar_result[2]

  g_menubar_dict = dict()

  """ explore_menu """
  def explore_menu(menu_id, label_list):
    global max_width
    global prefix
    global success

    if not menu_id in g_menubar_menus:
      return

    for menu in g_menubar_menus[menu_id]:
      label_set = 'label' in menu
      if label_set:
        label_list += [ menu['label'].replace('_', '') ]

      formatted_label = format_label_list(label_list).rstrip()
      w = len ( formatted_label )
      if w > max_width:
        max_width = w

      is_submenu = ':submenu' in menu

      if 'accel' in menu:
        accel = menu['accel']

        if len(accel) > 1:
          mch = '>' if accel.endswith('<') else '<'
          for r in (('<Primary>', 'Ctrl + '), ('<Alt>', 'Alt + '), ('<Shift>', 'Shift + ')):

            accel = accel.replace (*r, 1)
            if accel.find (mch) == -1:
              break
      else:
        accel = None

      if 'action' in menu:
        success = True
        action = menu['action']
        desc = g_action_object_iface.Describe (action.replace(act_prefix, ''))
        prefn = 1
        target = None

        if 'target' in menu:
          target = menu['target']
          prefn = 5 if (desc[2][0] == target) else 4
        elif len( desc[2] ) > 0:
          prefn = 3 if desc[2][0] else 2
        elif is_submenu:
          prefn = 0

        g_menubar_dict[formatted_label] = ( action, prefix[prefn], accel, target )

      if ':section' in menu:
        section = menu[':section']
        section_menu_id = (section[0], section[1])
        explore_menu(section_menu_id, label_list)

      if is_submenu:
        submenu = menu[':submenu']
        submenu_menu_id = (submenu[0], submenu[1])
        explore_menu(submenu_menu_id, label_list)

      if label_set:
        label_list.pop()

  explore_menu((0,0), [])
  max_width += 1
  max_width_str = str (max_width)

  # --- Run dmenu
  string = ''
  head, *tail = g_menubar_dict.keys()
  string = head
  for m in tail:
    act, pref, accel, targ = g_menubar_dict[m]
    string += '\n'
    string += pref

    if accel:
      string += ('{:<' + max_width_str + '}').format (m)
      if len(accel) > 0:
        string += kb_left + accel + kb_right
    else:
      string += m

  cmd = subprocess.Popen(dmenu_exe, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
  cmd.stdin.write(string.encode('utf-8'))
  result = cmd.communicate()[0].decode('utf-8').strip('\n')
  cmd.stdin.close()

  # --- Use dmenu result
  indent = 0
  for p in prefix[1:]:
    if result.startswith (p):
      indent = len (p)
      break

  result = result[indent:max_width+indent].rstrip()
  if result in g_menubar_dict:
    action, pref, accel, target = g_menubar_dict[result]
    param = []

    if target:
      param.append (target)
    print('GTK Action :', action)
    g_action_object_iface.Activate(action.replace(act_prefix, ''), param, dict())

def xprop_set(prop):
  return (prop.find(':') == -1) or not prop.split(':')[1] in ['  not found.\n', '  no such atom on any window.\n']

"""
  main
"""

# --- Get DMenu command ---
success = False
dmenu_exe = None
separator = ' > '
kb_left = '['
kb_right = ']'

opts, args = getopt(argv[1:], '', ['dmenu=', 'sep=', 'help', 'markup'])
for opt in opts:
  if opt[0] == '--dmenu':
    dmenu_exe = opt[1]
  elif opt[0] == '--sep':
    separator = opt[1]
  elif opt[0] == '--help':
    help()
    exit(0)
  elif opt[0] == '--markup':
    kb_left = '<b>'
    kb_right = '</b>'

if not dmenu_exe:
  dmenu_exe = getenv('DMENU')

if not dmenu_exe:
  dmenu_exe = 'dmenu -i -l 10'

dmenu_exe = dmenu_exe.split()

# --- Get X Window ID ---
window_id_cmd = subprocess.check_output(['xprop', '-root', '-notype', '_NET_ACTIVE_WINDOW']).decode('utf-8')
window_id = window_id_cmd.split('#')[1].split(',')[0].strip()

print('Window id is :', window_id)

# --- Get GTK MenuModel Bus name ---

g_bus_name_cmd = subprocess.check_output(['xprop', '-id', window_id, '-notype', '_GTK_UNIQUE_BUS_NAME']).decode('utf-8')
g_action_path_cmd = subprocess.check_output(['xprop', '-id', window_id, '-notype', '_GTK_WINDOW_OBJECT_PATH']).decode('utf-8')
g_menubar_path_cmd = subprocess.check_output(['xprop', '-id', window_id, '-notype', '_GTK_MENUBAR_OBJECT_PATH']).decode('utf-8')

g_app_path_cmd = subprocess.check_output(['xprop', '-id', window_id, '-notype', '_GTK_APPLICATION_OBJECT_PATH']).decode('utf-8')
g_appmenu_path_cmd = subprocess.check_output(['xprop', '-id', window_id, '-notype', '_GTK_APP_MENU_OBJECT_PATH']).decode('utf-8')

if xprop_set (g_bus_name_cmd):
  if xprop_set (g_menubar_path_cmd):
    if not xprop_set (g_action_path_cmd):
      g_action_path_cmd = g_menubar_path_cmd
      act_prefix = 'unity.'
    else:
      act_prefix = 'win.'
    try_gtk_interface(g_bus_name_cmd, g_menubar_path_cmd, g_action_path_cmd)
  if not success and xprop_set (g_app_path_cmd) and xprop_set (g_appmenu_path_cmd):
    act_prefix = 'app.'
    try_gtk_interface(g_bus_name_cmd, g_appmenu_path_cmd, g_app_path_cmd)
