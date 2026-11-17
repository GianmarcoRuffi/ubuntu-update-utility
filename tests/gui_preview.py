"""Render a native preview with sample rows; no worker or update is executed."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ubuntu_update.app import Utility
from gi.repository import GLib,Gtk,Graphene
app=Utility()
def populate():
    for identifier,name,current,available in [('archive:Postman','Postman','12.36.0','12.37.1'),('archive:Forge','Forge','2.0.15','2.0.16'),('snap:firefox','firefox','1','2')]:
        app.candidates[identifier]=dict(id=identifier,name=name,current=current,available=available,kind='Snap' if identifier.startswith('snap:') else 'Standalone')
    app.populate();app.rows['archive:Postman'].set_active(True)
    app.status.set_text('Anteprima con dati di esempio · seleziona le app da aggiornare.')
    GLib.timeout_add(600,capture)
    return False
def capture():
    content=app.win.get_content();width,height=content.get_width(),content.get_height()
    snapshot=Gtk.Snapshot()
    found,color=app.win.get_style_context().lookup_color('window_bg_color')
    assert found
    rectangle=Graphene.Rect();rectangle.init(0,0,width,height)
    snapshot.append_color(color,rectangle)
    Gtk.WidgetPaintable.new(content).snapshot(snapshot,width,height)
    node=snapshot.to_node();assert node
    texture=app.win.get_renderer().render_texture(node,None)
    target=Path(__file__).resolve().parents[1]/'dist/preview.png'
    texture.save_to_png(str(target))
    print('Native preview saved:',target)
    app.quit();return False
GLib.timeout_add(1000,populate)
app.run([])
