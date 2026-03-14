import sys
import gi
gi.require_version("Gst", "1.0")


from gi.repository import Gst, GLib


class DeepstreamPipeline:
    def __init__(self):
        self.pipeline : None | Gst.Pipeline = None
        self.loop : None | GLib.MainLoop = None
        self.bus : None | Gst.Bus = None
    def create_pipeline(self):

        print('creating pipeline')
        Gst.init(None)
        self.pipeline = Gst.Pipeline()
        if not self.pipeline:
            raise RuntimeError("Unable to create Pipeline")

        self.loop = GLib.MainLoop()

        source = Gst.ElementFactory.make("filec","filesource")
        if not source:
            raise RuntimeError("Unable to create source")


    def __enter__(self):
        self.create_pipeline()
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
def main():

    print("hello")
    try:
        with DeepstreamPipeline() as pipeline:
            print("pipeline running")
    except Exception as e:
        print(f"Unexpected error {e}")
    


if __name__ == "__main__":
    main()