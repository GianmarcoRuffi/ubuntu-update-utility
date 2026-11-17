import io
from ubuntu_update.runtime import Session
class FakeSession(Session):
    def __init__(self):super().__init__(io.StringIO());self.commands=[]
    def confirm(self,*args):return True
    def checkpoint(self):pass
    def command(self,args,**kwargs):self.commands.append(args);return 0
