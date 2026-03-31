import sys
sys.path.append('../')
import gi
gi.require_version("Gst", "1.0")
from common.bus_call import bus_call
import logging
from gi.repository import Gst, GLib

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DeepstreamPipeline:

    def __init__(self, file_name: str, output_file: str):
        self.file_name: str = file_name
        self.output_file: str = output_file
        self.pipeline: Gst.Pipeline | None = None
        self.loop: GLib.MainLoop | None = None
        self.bus: Gst.Bus | None = None
        Gst.init(None)
        logger.info("GStreamer initialized")

    def create_element(self, factory: str, name: str) -> Gst.Element:
        element = Gst.ElementFactory.make(factory, name)
        if not element:
            raise RuntimeError(f"Unable to create element '{name}' from factory '{factory}'")
        return element

    def add_element(self, element: Gst.Element) -> None:
        if not self.pipeline:
            raise RuntimeError("Pipeline not initialized")
        if not self.pipeline.add(element):
            raise RuntimeError(f"Unable to add element '{element.get_name()}' to pipeline")

    def link_elements(self, element1: Gst.Element, element2: Gst.Element) -> None:
        if not element1.link(element2):
            raise RuntimeError(
                f"Unable to link '{element1.get_name()}' → '{element2.get_name()}'"
            )

    def create_pipeline(self) -> None:
        logger.info("Creating pipeline")
        self.pipeline = Gst.Pipeline()

        # --- Phase 1: Demux & Decode (CPU → GPU) ---
        # filesrc → h264parse → nvv4l2decoder
        source      = self.create_element("filesrc",        "file-source")
        h264parser  = self.create_element("h264parse",      "h264-parser")
        decoder     = self.create_element("nvv4l2decoder",  "nvv4l2-decoder")

        # --- Phase 2: Batch & Infer (GPU, NV12) ---
        # nvstreammux → nvinfer
        streammux   = self.create_element("nvstreammux",    "stream-muxer")
        pgie        = self.create_element("nvinfer",        "primary-inference")

        # --- Phase 3: OSD — Draw Bounding Boxes (GPU, RGBA) ---
        # nvvideoconvert(NV12→RGBA) → nvdsosd → nvvideoconvert(RGBA→I420)
        nvvidconv1  = self.create_element("nvvideoconvert", "convertor-1")
        nvosd       = self.create_element("nvdsosd",        "on-screen-display")
        nvvidconv2  = self.create_element("nvvideoconvert", "convertor-2")
        capsfilter  = self.create_element("capsfilter",     "caps-filter")

        # --- Phase 4: Encode & Mux → MP4 (GPU → CPU → Disk) ---
        # nvv4l2h264enc → h264parse → mp4mux → filesink
        encoder     = self.create_element("nvv4l2h264enc",  "h264-encoder")
        h264parse2  = self.create_element("h264parse",      "h264-parser-encoder")
        mp4mux      = self.create_element("qtmux",          "mp4-muxer")
        filesink    = self.create_element("filesink",       "file-sink")

        # --- Configure Properties ---
        source.set_property("location", self.file_name)

        streammux.set_property("batch-size", 1)
        streammux.set_property("width", 1280)
        streammux.set_property("height", 720)
        streammux.set_property("batched-push-timeout", 33000)

        pgie.set_property("config-file-path", "dstest1_pgie_config.txt")

        # CRITICAL: Keep frames in GPU memory (NVMM) as I420 for the hardware encoder
        caps = Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420")
        capsfilter.set_property("caps", caps)

        encoder.set_property("bitrate", 4000000)  # 4 Mbps

        filesink.set_property("location", self.output_file)
        filesink.set_property("sync", 0)
        filesink.set_property("async", 0)

        # --- Add All Elements to Pipeline ---
        for el in [source, h264parser, decoder, streammux, pgie,
                   nvvidconv1, nvosd, nvvidconv2, capsfilter,
                   encoder, h264parse2, mp4mux, filesink]:
            self.add_element(el)

        # --- Link Elements ---
        # Phase 1: filesrc → h264parse → nvv4l2decoder
        self.link_elements(source, h264parser)
        self.link_elements(h264parser, decoder)

        # decoder uses a dynamic src pad, streammux uses request sink pads
        srcpad = decoder.get_static_pad("src")
        sinkpad = streammux.request_pad_simple("sink_0")
        if not srcpad or not sinkpad:
            raise RuntimeError("Failed to get decoder src pad or streammux sink pad")
        srcpad.link(sinkpad)

        # Phase 2: streammux → nvinfer
        self.link_elements(streammux, pgie)

        # Phase 3: nvinfer → nvvidconv1(NV12→RGBA) → nvdsosd → nvvidconv2(RGBA→I420 NVMM)
        self.link_elements(pgie, nvvidconv1)
        self.link_elements(nvvidconv1, nvosd)
        self.link_elements(nvosd, nvvidconv2)
        self.link_elements(nvvidconv2, capsfilter)

        # Phase 4: capsfilter → encoder → h264parse → mp4mux → filesink
        self.link_elements(capsfilter, encoder)
        self.link_elements(encoder, h264parse2)
        self.link_elements(h264parse2, mp4mux)
        self.link_elements(mp4mux, filesink)

        logger.info("All elements linked successfully")

        # --- Setup Bus & Main Loop ---
        self.loop = GLib.MainLoop()
        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", bus_call, self.loop)

        self.start_pipeline()

    def start_pipeline(self) -> None:
        if not self.pipeline or not self.loop:
            raise RuntimeError("Pipeline or loop not initialized")

        logger.info(f"Starting pipeline → saving to '{self.output_file}'")
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Unable to set pipeline to PLAYING state")

        try:
            self.loop.run()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        logger.info("Cleaning up pipeline")
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)

    def __enter__(self):
        self.create_pipeline()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 app.py <input_file.h264> <output_file.mp4>")
        sys.exit(1)

    file_name = sys.argv[1]
    output_file = sys.argv[2]

    try:
        with DeepstreamPipeline(file_name, output_file):
            pass
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
