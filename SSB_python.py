import socket
import threading
from gnuradio import gr
from gnuradio import soapy
from gnuradio import audio
from gnuradio import filter
from gnuradio import blocks
from gnuradio.filter import firdes
from gnuradio.filter import window  # Import window module for Hamming

class TXFlowgraph(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "TX Flowgraph")
        self.audio_source = audio.source(48000, "", True)
        taps = firdes.complex_band_pass(
            gain=1.0,              # Gain: 1
            sampling_freq=48000,   # Sample Rate: 48k
            low_cutoff_freq=300,   # Low Cutoff Freq: 300 Hz
            high_cutoff_freq=3600, # High Cutoff Freq: 3600 Hz
            transition_width=200,  # Transition Width: 200 Hz
            window=window.WIN_HAMMING  # Window: Hamming
        )
        self.ssb_filter = filter.freq_xlating_fir_filter_fcc(
            decimation=1,          # Decimation: 1
            taps=taps,             # Complex bandpass taps
            center_freq=0,         # Center at 0 Hz (baseband USB)
            sampling_freq=48000    # Input sample rate (matches audio source)
        )
        self.resampler = filter.rational_resampler_ccf(
            interpolation=125,
            decimation=3
        )
        self.sink = soapy.sink("driver=hackrf", "fc32", 1, "", "", [""], [""])
        self.sink.set_sample_rate(0, 2e6)
        self.sink.set_gain(0, "AMP", 14)
        self.sink.set_gain(0, "VGA", 47)
        self.connect((self.audio_source, 0), (self.ssb_filter, 0))
        self.connect((self.ssb_filter, 0), (self.resampler, 0))
        self.connect((self.resampler, 0), (self.sink, 0))

class RXFlowgraph(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "RX Flowgraph")

        # HackRF source
        self.source = soapy.source("driver=hackrf", "fc32", 1, "", "", [""], [""])
        self.source.set_sample_rate(0, 2e6)
        self.source.set_gain(0, "AMP", 14)
        self.source.set_gain(0, "LNA", 40)
        self.source.set_gain(0, "VGA", 40)

        # Early decimation to exactly 48 kHz
        self.resampler = filter.rational_resampler_ccf(
            interpolation=3,
            decimation=125  # 2e6 * 3 / 125 = 48000 Hz
        )

        # SSB demodulation filter (USB) at 48 kHz
        taps = firdes.complex_band_pass(
            gain=1.0,
            sampling_freq=48000,   # Matches resampler output
            low_cutoff_freq=300,   # Match TX: 300 Hz
            high_cutoff_freq=3600, # Match TX: 3600 Hz
            transition_width=200,
            window=window.WIN_HAMMING
        )
        self.ssb_demod = filter.freq_xlating_fir_filter_ccc(
            decimation=1,
            taps=taps,
            center_freq=0,         # No additional shift
            sampling_freq=48000    # Input sample rate
        )

        # DC blocker
        self.dc_blocker = filter.dc_blocker_cc(
            D=32,                  # Filter length
            long_form=True         # Full FIR filter
        )

        # Complex to float (real audio)
        self.complex_to_float = blocks.complex_to_float(1)

        # Audio sink
        self.audio_sink = audio.sink(48000, "", True)

        # Connections
        self.connect((self.source, 0), (self.resampler, 0))
        self.connect((self.resampler, 0), (self.ssb_demod, 0))
        self.connect((self.ssb_demod, 0), (self.dc_blocker, 0))
        self.connect((self.dc_blocker, 0), (self.complex_to_float, 0))
        self.connect((self.complex_to_float, 0), (self.audio_sink, 0))

def rig_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("127.0.0.1", 4575))
    server_socket.listen(1)
    print("Rig server listening on 127.0.0.1:4575")

    try:
        tx_fg = TXFlowgraph()
        rx_fg = RXFlowgraph()
    except Exception as e:
        print(f"Failed to initialize flowgraphs: {e}")
        return

    # Start with TX flowgraph, then flip to RX
    active_fg = tx_fg  # Start with TX flowgraph
    try:
        active_fg.start()
        print("Started TX flowgraph briefly")
        active_fg.stop()
        active_fg.wait()
        print("Stopped TX flowgraph")
        active_fg = rx_fg  # Flip to RX flowgraph
        active_fg.start()
        print("Started RX flowgraph")
    except Exception as e:
        print(f"Failed to initialize TX/RX sequence: {e}")
        return
    tx_active = False  # Now in RX mode

    while True:
        client_socket, addr = server_socket.accept()
        print(f"Client connected from {addr}")
        try:
            while True:
                data = client_socket.recv(1024).decode().strip()
                if not data:
                    print(f"Client {addr} disconnected")
                    break
                print(f"Received: {data}")

                if data.lower() == "f" or data.lower() == "f vfoa":
                    freq = (active_fg.sink.get_frequency(0) if tx_active
                            else active_fg.source.get_frequency(0))
                    client_socket.send(f"{int(freq)}\r\n".encode())
                    print(f"Sent frequency: {int(freq)}")
                elif data.lower().startswith("f ") or data.lower().startswith("f vfoa "):
                    try:
                        parts = data.split()
                        freq_index = 1 if len(parts) == 2 else 2 if len(parts) == 3 and parts[1].lower() == "vfoa" else -1
                        if freq_index == -1:
                            raise ValueError("Invalid frequency command format")
                        new_freq = float(parts[freq_index])
                        if tx_active:
                            active_fg.sink.set_frequency(0, new_freq)
                        else:
                            active_fg.source.set_frequency(0, new_freq)
                        client_socket.send(b"RPRT 0\r\n")
                        print(f"Set HackRF {'TX' if tx_active else 'RX'} frequency to {new_freq/1e6} MHz")
                    except (ValueError, IndexError) as e:
                        client_socket.send(b"RPRT -1\r\n")
                        print(f"Error parsing frequency: {e}")
                elif data == "\\dump_state":
                    response = (
                        "0\r\n"
                        "2\r\n"
                        "1\r\n"
                        "0.000000 10000000000.000000 0xef -1 -1 0x1 0x0\r\n"
                        "0 0 0 0 0 0 0\r\n"
                        "0 0 0 0 0 0 0\r\n"
                        "0xef 1\r\n"
                        "0xef 0\r\n"
                        "0 0\r\n"
                        "0x82 500\r\n"
                        "0x82 200\r\n"
                        "0x82 2000\r\n"
                        "0x21 10000\r\n"
                        "0x21 5000\r\n"
                        "0x21 20000\r\n"
                        "0x0c 2700\r\n"
                        "0x0c 1400\r\n"
                        "0x0c 3900\r\n"
                        "0x40 160000\r\n"
                        "0x40 120000\r\n"
                        "0x40 200000\r\n"
                        "0 0\r\n"
                        "0\r\n"
                        "0\r\n"
                        "0\r\n"
                        "0\r\n"
                        "0\r\n"
                        "0\r\n"
                        "0\r\n"
                        "0\r\n"
                        "0x40000020\r\n"
                        "0x20\r\n"
                        "0\r\n"
                        "0\r\n"
                    )
                    client_socket.send(response.encode())
                    print("Sent custom dump_state response")
                elif data == "\\get_powerstat":
                    client_socket.send(b"1\r\n")
                    print("Sent power status: 1 (On)")
                elif data == "\\chk_vfo":
                    client_socket.send(b"CHKVFO 0\r\n")
                    print("Sent CHKVFO 0")
                elif data.lower() == "v":
                    client_socket.send(b"RPRT -11\r\n")
                    print("Sent RPRT -11 for invalid command 'v'")
                elif data.lower() == "s" or data.lower() == "s vfoa":
                    client_socket.send(b"0\r\nVFOA\r\n")
                    print("Sent split: 0, VFO: VFOA")
                elif data.lower() == "s vfoa 0 vfoa":
                    client_socket.send(b"RPRT -1\r\nRPRT -1\r\n")
                    print("Sent RPRT -1 RPRT -1 for invalid command 'S VFOA 0 VFOA'")
                elif data.lower() == "t" or data.lower() == "t vfoa":
                    response = b"1\r\n" if tx_active else b"0\r\n"
                    client_socket.send(response)
                    print(f"Sent active flowgraph state: {'TX' if tx_active else 'RX'}")
                elif data.lower() == "q":
                    try:
                        if tx_active:  # If in TX mode, switch to RX
                            active_fg.stop()
                            active_fg.wait()
                            active_fg = rx_fg
                            active_fg.start()
                            tx_active = False
                            print("Dropped to RX mode on 'q'")
                        client_socket.send(b"RPRT 0\r\n")
                        print("Sent RPRT 0 for quit command 'q'")
                        break  # Disconnect client, keep server running
                    except Exception as e:
                        client_socket.send(b"RPRT -1\r\n")
                        print(f"Error handling 'q': {e}")
                        break
                elif data.lower() == "t 1" or data.lower() == "t vfoa 1":
                    try:
                        if not tx_active:
                            active_fg.stop()
                            active_fg.wait()
                            active_fg = tx_fg
                            active_fg.start()
                            tx_active = True
                        client_socket.send(b"RPRT 0\r\n")
                        print("Transmit enabled (PTT on)")
                    except Exception as e:
                        client_socket.send(b"RPRT -1\r\n")
                        print(f"Error enabling TX: {e}")
                elif data.lower() == "t 0" or data.lower() == "t vfoa 0":
                    try:
                        if tx_active:
                            active_fg.stop()
                            active_fg.wait()
                            active_fg = rx_fg
                            active_fg.start()
                            tx_active = False
                        client_socket.send(b"RPRT 0\r\n")
                        print("Transmit disabled (RX mode enabled)")
                    except Exception as e:
                        client_socket.send(b"RPRT -1\r\n")
                        print(f"Error enabling RX: {e}")
                else:
                    client_socket.send(b"RPRT -1\r\n")
                    print(f"Unknown command: {data}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            client_socket.close()
            print(f"Connection closed for {addr}")

if __name__ == "__main__":
    server_thread = threading.Thread(target=rig_server, args=(), daemon=True)
    server_thread.start()
    try:
        while True:
            pass  # Keep main thread alive
    except KeyboardInterrupt:
        print("Shutting down")
        if 'active_fg' in locals():  # Check if active_fg is defined
            active_fg.stop()
            active_fg.wait()
        if 'server_socket' in locals():  # Check if server_socket is defined
            server_socket.close()
