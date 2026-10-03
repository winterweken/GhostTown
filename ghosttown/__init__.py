"""GhostTown: site context from open data, built as clean geometry."""
import bpy

from . import ops, prefs, props, runner, ui

_CLASSES = (
    prefs.GhostTownPreferences,
    props.GhostTownSettings,
    ops.GHOSTTOWN_OT_import_context,
    ops.GHOSTTOWN_OT_build,
    ops.GHOSTTOWN_OT_cancel,
    ui.GHOSTTOWN_PT_main,
)


@bpy.app.handlers.persistent
def _on_load_pre(*_args):
    runner.cancel_all()  # a fetch never outlives the file it was started from


def _remove_handler():
    for handler in list(bpy.app.handlers.load_pre):
        if getattr(handler, "__name__", "") == "_on_load_pre" and getattr(handler, "__module__", "") == __name__:
            bpy.app.handlers.load_pre.remove(handler)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ghosttown = bpy.props.PointerProperty(type=props.GhostTownSettings)
    _remove_handler()
    bpy.app.handlers.load_pre.append(_on_load_pre)


def unregister():
    runner.cancel_all()
    _remove_handler()
    del bpy.types.Scene.ghosttown
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
