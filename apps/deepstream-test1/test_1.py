import sys
from os import path
sys.path.append('../')
from common.bus_call import bus_call
import gi
import pyds
gi.require_version("Gst","1.0")
from gi.repository import Gst, GLib

def osd_callback(pad : Gst.Pad, info: Gst.PadProbeInfo) -> Gst.PadProbeReturn:
    buffer : None | Gst.Buffer = info.get_buffer()
    if not buffer:
        return Gst.PadProbeReturn.OK;

    batch_meta : None | pyds.NvDsBatchMeta =  pyds.gst_buffer_get_nvds_batch_meta(hash(buffer))
    if not batch_meta:
        return Gst.PadProbeReturn.OK

    l_frame = batch_meta.frame_meta_list

    while l_frame is not None:
        try:
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            frame_num = frame_meta.frame_num
            print(frame_num)
        except StopIteration:
            break
        l_frame = l_frame.next
     


    return Gst.PadProbeReturn.OK

def main():

    print("Initialising Deepstream Test 1")
    Gst.init(None)
    file_path = '../../samples/streams/sample_720p.h264'

    # check if file exists
    if not path.isfile(file_path):
        raise FileNotFoundError(f"Input file not found at {file_path}" )

    pipeline = Gst.Pipeline()
    # read the raw bytes. these are not h264 timed yet
    filesrc = Gst.ElementFactory.make("filesrc", "file-source")
    if not filesrc:
        raise ValueError("Unable to create filesrc")
    filesrc.set_property("location", file_path)
    pipeline.add(filesrc)
    # convert raw bytes into the h264 timed bytes, NAL units video-xraw/h264-timed, in RAM
    h264parser = Gst.ElementFactory.make("h264parse","h264-parser")
    if not h264parser:
        raise ValueError("Unable to create element: h264parser")

    pipeline.add(h264parser)
    # convert to raw frames and move to NVMM , output video-xraw/NVMM
    decoder = Gst.ElementFactory.make("nvv4l2decoder", "decoder")
    if not decoder:
        raise ValueError("Unable to create element nvv4l2decoder")
    pipeline.add(decoder)

    # batch the files for inferencing
    streammux = Gst.ElementFactory.make("nvstreammux", "streammux")
    if not streammux: 
        raise ValueError("unable to create streammux")
    streammux.set_property("batch-size", 1)
    streammux.set_property("width", 1920)
    streammux.set_property("height", 1080)
    pipeline.add(streammux)

    # Perform inferencing
    pgie = Gst.ElementFactory.make("nvinfer", "pgie")
    if not pgie:
        raise ValueError("Unable to create PGIE")
    pgie.set_property("config-file-path", "./dstest1_pgie_config.txt")
    pipeline.add(pgie)

    # NVIDIA Deepstream on screen display: convert the raw RGBA frame/buffer into i420 to be used by osd
    nvvideoconv = Gst.ElementFactory.make("nvvideoconvert", "converter")
    if not nvvideoconv:
        raise ValueError("Unable to create element nvvideoconvert")
    pipeline.add(nvvideoconv)

    osd = Gst.ElementFactory.make("nvdsosd","osd" )
    if not osd: 
        raise ValueError("Unable to create element: osd")
    pipeline.add(osd)
    ## output is RGBA

    converter2 = Gst.ElementFactory.make("nvvideoconvert", "converter2")
    if not converter2:
        raise ValueError("Unable to create converter2")
    pipeline.add(converter2)

    encoder = Gst.ElementFactory.make("nvv4l2h264enc", "encoder")
    if not encoder:
        raise ValueError("Unable to create encoder")
    pipeline.add(encoder)

    h264parser_2 = Gst.ElementFactory.make("h264parse", "parser2")    
    if not h264parser_2:
        raise ValueError("Unable to create h264parser_2")
    pipeline.add(h264parser_2)
    
    muxer = Gst.ElementFactory.make("mp4mux", "muxer")
    if not muxer:
        raise ValueError("Unablet to create muxer")
    pipeline.add(muxer)

    # create fakesink
    sink = Gst.ElementFactory.make("filesink", "sink")
    if not sink:
        raise ValueError("Unable to create sink")
    pipeline.add(sink)
    print("Link elements")
    if not filesrc.link(h264parser):
        raise RuntimeError("Unable to link filesrc with h264parser")

    if not h264parser.link(decoder):
        raise RuntimeError("Unablet to link h264parser with nvv4l2decoder")
    
    srcpad = decoder.get_static_pad("src")
    if not srcpad:
        raise ValueError("Unable to get source pad from the decoder")
    sinkpad = streammux.request_pad_simple("sink_0")

    if not sinkpad:
        raise ValueError("Unable to get sinkpad from the streammux")

    if srcpad.link(sinkpad) != Gst.PadLinkReturn.OK:
        raise RuntimeError(f"Unable to link decoder to streammux ")

    if not streammux.link(pgie):
        raise RuntimeError("Unable to link streammux with pgie")
    
    
    if not pgie.link(nvvideoconv):
        raise RuntimeError("Unable to link pgie to nvvideoconvert")
    
    if not nvvideoconv.link(osd):
        raise RuntimeError("Unable to link nvvideoconvert to osd")

    if not osd.link(converter2):
        raise RuntimeError("Unable to link osd to converter2") 
    
    if not converter2.link(encoder):
        raise RuntimeError("Unablet to link converter 2 to encoder")
    
    if not encoder.link(h264parser_2):
        raise RuntimeError("Unable to link encoder to h264parser2")
    
    if not h264parser_2.link(muxer):
        raise RuntimeError("Unable to link h264parser_2 to muxer")
    sink.set_property("location","output_1.mp4")
    if not muxer.link(sink):
        raise RuntimeError("unable to link muxer to sink")

    osd_sink_pad: Gst.Pad | None = osd.get_static_pad("sink")
    if not osd_sink_pad:
        raise ValueError("Unable to get osd_sink_pad")
    osd_sink_pad.add_probe(Gst.PadProbeType.BUFFER, osd_callback)


    # Start pipeline
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    loop : GLib.MainLoop | None = GLib.MainLoop()
    if not loop:
        raise RuntimeError("cannot create main loop")
    bus.connect("message", bus_call, loop)
    playing_state_return = pipeline.set_state(Gst.State.PLAYING)
    if playing_state_return == Gst.StateChangeReturn.FAILURE:
        raise RuntimeError("Unable to start")

    Gst.debug_bin_to_dot_file(pipeline, Gst.DebugGraphDetails.ALL, "my_deepstream_pipeline")

    try:
        loop.run()
    except Exception as e:
        print(f"error {e}")
    finally:
        print("cleaning up pipeline")
        pipeline.set_state(Gst.State.NULL)

if __name__ == "__main__":
   main()
