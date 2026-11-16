import bundled   # must be imported first: it patches main and vision
import gui
import updater, version

_orig_init = gui.App.__init__

def _init(self, root):
    _orig_init(self, root)
    root.title(f"ChessHelper v{version.VERSION}")
    root.after(1500, lambda: updater.check_async(root, self.log))

gui.App.__init__ = _init

if __name__ == "__main__":
    gui.run_app()