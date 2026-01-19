import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
import gettext
import locale

from action_widget import ActionWidget
from gi.repository import Adw, Gtk

# Set up gettext for application localization.
DOMAIN = "biglinux-welcome"
LOCALE_DIR = "/usr/share/locale"
locale.setlocale(locale.LC_ALL, "")
locale.bindtextdomain(DOMAIN, LOCALE_DIR)
locale.textdomain(DOMAIN)
gettext.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.textdomain(DOMAIN)
_ = gettext.gettext


class WelcomePage(Adw.Bin):
    """A page for the welcome carousel, displaying a title and a grid of actions."""

    def __init__(self, page_data, **kwargs):
        super().__init__(**kwargs)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(36)
        main_box.set_margin_end(36)
        self.set_child(main_box)

        # Title and Subtitle Area
        title_label = Gtk.Label(halign=Gtk.Align.CENTER)
        title_label.set_markup(
            f"<span size='xx-large' weight='bold'>{_(page_data['title'])}</span>"
        )
        main_box.append(title_label)

        # subtitle_label = Gtk.Label(halign=Gtk.Align.CENTER)
        # subtitle_label.set_markup(f"<span size='large'>{_(page_data['subtitle'])}</span>")
        # main_box.append(subtitle_label)

        subtitle_label = Gtk.Label(halign=Gtk.Align.CENTER)
        subtitle_label.set_markup(
            f"<span size='large'>{_(page_data['subtitle'])}</span>"
        )

        # Enable text wrapping for the subtitle
        subtitle_label.set_wrap(True)

        main_box.append(subtitle_label)

        if page_data.get("title") == "KDE Connect":
            # Custom layout for KDE Connect
            scrolled_window = Gtk.ScrolledWindow(vexpand=True)
            scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            
            custom_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
            custom_box.set_halign(Gtk.Align.CENTER)
            custom_box.set_valign(Gtk.Align.CENTER)
            custom_box.set_margin_top(20)
            custom_box.set_margin_bottom(20)
            scrolled_window.set_child(custom_box)
            
            main_box.append(scrolled_window)

            actions = {action["label"]: action for action in page_data["actions"]}
            
            # Top: KDE Connect
            if "KDE Connect" in actions:
                action = actions["KDE Connect"]
                widget = ActionWidget(
                    label=_(action["label"]),
                    icon_name=action["icon"],
                    action_type=action["type"],
                    command=action.get("command", ""),
                )
                widget.set_halign(Gtk.Align.CENTER)
                custom_box.append(widget)

            # Bottom: Stores
            stores_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=30)
            stores_box.set_halign(Gtk.Align.CENTER)
            custom_box.append(stores_box)

            for label in ["PlayStore", "AppStore"]:
                if label in actions:
                    action = actions[label]
                    widget = ActionWidget(
                        label=_(action["label"]),
                        icon_name=action["icon"],
                        action_type=action["type"],
                        command=action.get("command", ""),
                    )
                    stores_box.append(widget)

        else:
            # Action Buttons Grid
            flowbox = Gtk.FlowBox(valign=Gtk.Align.START, max_children_per_line=5)
            flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
            flowbox.set_halign(Gtk.Align.CENTER)

            scrolled_window = Gtk.ScrolledWindow(vexpand=True)
            scrolled_window.set_child(flowbox)
            scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            main_box.append(scrolled_window)

            for action in page_data["actions"]:
                widget = ActionWidget(
                    label=_(action["label"]),
                    icon_name=action["icon"],
                    action_type=action["type"],
                    command=action.get("command", ""),
                )
                flowbox.insert(widget, -1)
