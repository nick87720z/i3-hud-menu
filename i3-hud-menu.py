#!/usr/bin/env python3

import dbus
import subprocess

from sys import argv
from getopt import getopt
from os import getenv

max_width = 0

def help():
  print ("Usage:")
  print (" " + argv[0] + " [--dmenu=CMD] [--sep=SEPARATOR] [--markup]")

"""
  format_label_list
"""
def format_label_list(label_list):
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
def try_gtk_interface(gtk_bus_name_cmd, gtk_object_path_cmd):
  global max_width

  gtk_bus_name = gtk_bus_name_cmd.split(' ')[2].split('\n')[0].split('"')[1]
  print(gtk_object_path_cmd)
  gtk_object_path = gtk_object_path_cmd.split(' ')[2].split('\n')[0].split('"')[1]
  print("GTK MenuModel Bus name and object path: ", gtk_bus_name, gtk_object_path)

  # --- Ask for menus over DBus ---
  session_bus = dbus.SessionBus()
  gtk_menubar_object = session_bus.get_object(gtk_bus_name, gtk_object_path)
  gtk_menubar_object_iface = dbus.Interface(gtk_menubar_object, dbus_interface='org.gtk.Menus')
  gtk_action_object_actions_iface = dbus.Interface(gtk_menubar_object, dbus_interface='org.gtk.Actions')
  gtk_menubar_results = gtk_menubar_object_iface.Start([x for x in range(1024)])

  if len(gtk_menubar_results) == 0:
    return

  # --- Construct menu list ---
  gtk_menubar_menus = dict()
  for gtk_menubar_result in gtk_menubar_results:
    gtk_menubar_menus[(gtk_menubar_result[0], gtk_menubar_result[1])] = gtk_menubar_result[2]

  gtk_menubar_action_dict = dict()
  gtk_menubar_target_dict = dict()
  gtk_menubar_accel_dict  = dict()
  gtk_menubar_prefix_dict = dict()

  """ explore_menu """
  def explore_menu(menu_id, label_list):
    global max_width

    prefix = ['    ' ,
              '[ ] ' ,
              '[x] ' ,
              '( ) ' ,
              '(x) ' ]

    if not menu_id in gtk_menubar_menus:
      return

    for menu in gtk_menubar_menus[menu_id]:
      if 'label' in menu:
        menu_label = menu['label'].replace('_', '')
      else:
        menu_label = '?'

      new_label_list = label_list + [menu_label]
      formatted_label = format_label_list(new_label_list).rstrip()
      w = len ( formatted_label )
      if w > max_width:
        max_width = w

      if 'accel' in menu:
        menu_accel = menu['accel'].replace('<Primary>', 'Ctrl + ').replace('<Shift>', 'Shift + ')
        gtk_menubar_accel_dict[formatted_label] = menu_accel

      if 'action' in menu:
        menu_action = menu['action']
        gtk_menubar_action_dict[formatted_label] = menu_action

        desc = gtk_action_object_actions_iface.Describe (menu_action.replace('unity.', ''))
        prefn = 0
        if len( desc[2] ) > 0:
          prefn = 2 if desc[2][0] else 1
        gtk_menubar_prefix_dict[formatted_label] = prefix[prefn]

        if 'target' in menu:
          menu_target = menu['target']
          gtk_menubar_target_dict[formatted_label] = menu_target

      if ':section' in menu:
        menu_section = menu[':section']
        section_menu_id = (menu_section[0], menu_section[1])
        explore_menu(section_menu_id, label_list)

      if ':submenu' in menu:
        menu_submenu = menu[':submenu']
        submenu_menu_id = (menu_submenu[0], menu_submenu[1])
        explore_menu(submenu_menu_id, new_label_list)

  explore_menu((0,0), [])
  max_width += 1
  max_width_str = str (max_width)

  # --- Run dmenu
  dmenu_string = ''
  head, *tail = gtk_menubar_action_dict.keys()
  dmenu_string = head
  for m in tail:
    dmenu_string += '\n'
    dmenu_string += gtk_menubar_prefix_dict[m]
    if m in gtk_menubar_accel_dict:
      dmenu_string += ('{:<' + max_width_str + '}').format (m)
      accel = gtk_menubar_accel_dict[m]
      if len(accel) > 0:
        dmenu_string += kb_left + accel + kb_right
    else:
      dmenu_string += m

  dmenu_cmd = subprocess.Popen(dmenu_exe, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
  dmenu_cmd.stdin.write(dmenu_string.encode('utf-8'))
  dmenu_result = dmenu_cmd.communicate()[0].decode('utf-8').strip('\n')
  dmenu_cmd.stdin.close()

  # --- Use dmenu result
  dmenu_result = dmenu_result[4:max_width+4].rstrip()
  if dmenu_result in gtk_menubar_action_dict:
    action = gtk_menubar_action_dict[dmenu_result]
    param = []
    if dmenu_result in gtk_menubar_target_dict:
      param.append (gtk_menubar_target_dict[dmenu_result])
    print('GTK Action :', action)
    gtk_action_object_actions_iface.Activate(action.replace('unity.', ''), param, dict())

def xprop_set(prop):
  return (prop.find(':') == -1) or not prop.split(':')[1] in ['  not found.\n', '  no such atom on any window.\n']

"""
  main
"""

# --- Get DMenu command ---
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

gtk_bus_name_cmd = subprocess.check_output(['xprop', '-id', window_id, '-notype', '_GTK_UNIQUE_BUS_NAME']).decode('utf-8')
gtk_object_path_cmd = subprocess.check_output(['xprop', '-id', window_id, '-notype', '_GTK_MENUBAR_OBJECT_PATH']).decode('utf-8')

if not xprop_set (gtk_bus_name_cmd) or not xprop_set (gtk_object_path_cmd):
  try_appmenu_interface(int(window_id, 16))
else:
  try_gtk_interface(gtk_bus_name_cmd, gtk_object_path_cmd)
