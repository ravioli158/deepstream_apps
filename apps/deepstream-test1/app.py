import sys
import gi
gi.require_version("Gst", "1.0")


from gi.repository import Gst, GLib


class DeepstreamPipeline:
    def __init__(self, file_name: str):

        self.file_name : None | str = file_name
        self.pipeline : None | Gst.Pipeline = None
        self.loop : None | GLib.MainLoop = None
        self.bus : None | Gst.Bus = None

    def create_element(self,factory: str, name: str):
        element = Gst.ElementFactory.make(factory, name)
        if not element:
            raise RuntimeError(f"Unable to create element {name}")
        return element


    def add_element(self, element: Gst.Element):
        if not element:
            raise RuntimeError("Pass valid element")

        if not isinstance(element, Gst.Element):
            raise TypeError(f"Expected Gst.Element, got {type(element)}")

        if not self.pipeline:
            raise RuntimeError(f"Pipeline not available")
        
        if not self.pipeline.add(element):
            raise RuntimeError(f"Unable to add element {element.get_name()}")

    def link_elements(self, element1: Gst.Element, element2: Gst.Element):
        if element1 is None or element2 is None:
            raise RuntimeError("Elements cannot be null")
        if not isinstance(element1, Gst.Element) or not isinstance(element2, Gst.Element):
            raise ValueError("Pass Gst.Element")
        
        ret = element1.link(element2)
        if not ret:
            raise RuntimeError("Unable to link elements")

    def create_pipeline(self):

        print('creating pipeline')
        Gst.init(None)
        self.pipeline = Gst.Pipeline()
        if not self.pipeline:
            raise RuntimeError("Unable to create Pipeline")

        self.loop = GLib.MainLoop()

        source = self.create_element("filesrc", "filesource")
        encoder = self.create_element("nvv4l2h264enc", "h264-encoder")
        parser = self.create_element("h264parse", "parser") 
        muxer = self.create_element("qtmux", "muxer")
        sink = self.create_element("filesink", "filesink")

        self.add_element(source)
        self.add_element(encoder)
        self.add_element(parser)
        self.add_element(muxer)
        self.add_element(sink)
        source.set_property("location", self.file_name)
        sink.set_property("location","tutorial_output.mp4")

        self.link_elements(source, encoder)
        self.link_elements(encoder, parser)
        self.link_elements(parser, muxer)
        self.link_elements(muxer, sink)


    def start_pipeline(self):
        self.pipeline.set_state(Gst.State.)
        
    def __enter__(self):
        self.create_pipeline()
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
def main():

    if not (len(sys.argv) == 2):
        print("Usage sample.mp4") 
        sys.exit(1)
    
    file_name = sys.argv[1]

    try:
        with DeepstreamPipeline(file_name) as pipeline:
            print("pipeline running")
    except Exception as e:
        print(f"Unexpected error {e}")
    


if __name__ == "__main__":
    main()