import sys
sys.path.append('../')
import os
import gi
gi.require_version("Gst", "1.0")
from common.bus_call import bus_call


from gi.repository import Gst, GLib
sys.path.append('../')
from common.platform_info import PlatformInfo


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
        
        source = self.create_element("filesrc", "filesource")
        h264parser = self.create_element("h264parse", "h264-parser")
        decoder = self.create_element("nvv4l2decoder", "nvv4l2-decoder")
        # Create nvstreammux instace to form batches from one or more sources
        streammux = self.create_element("nvstreammux", "Stream-muxer") 

        pgie = self.create_element("nvinfer", "inference")

        nvvidconv = self.create_element("nvvideoconvert", "convertor")

        # Create OSD to draw on the converted RGBA buffer
        nvosd = self.create_element("nvdsosd", "osd")
        sink = self.create_element("nveglglessink", "nvvideo-renderer")

        source.set_property("location", self.file_name)
        streammux.set_property('batch-size', 1)
        pgie.set_property('config-file-path', 'dstest1_pgie_config.txt')


        print("Adding elements to pipeline")
        self.add_element(source) 
        self.add_element(h264parser)
        self.add_element(decoder)
        self.add_element(streammux)
        self.add_element(pgie)
        self.add_element(nvvidconv)
        self.add_element(nvosd)
        self.add_element(sink)

        print("Linking elements")
        self.link_elements(source, h264parser)
        self.link_elements(h264parser, decoder)
        srcpad = decoder.get_static_pad("src")
        if not srcpad:
            raise RuntimeError("unable to get src pad")

        sinkpad = streammux.request_pad_simple("sink_0")
        if not sinkpad:
            raise RuntimeError("Unable to get the sink pad of the streammux")

        srcpad.link(sinkpad)
        streammux.link(pgie)        
        pgie.link(nvvidconv)
        nvvidconv.lik(nvosd)
        nvosd.link(sink)

        self.loop = GLib.MainLoop()
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", bus_call, loop)
        
        self.start_pipeline()


    def start_pipeline(self):
        self.bus = self
        self.pipeline.set_state(Gst.State.PLAYING)
        try:
            self.loop.run()
        except:
            pass

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