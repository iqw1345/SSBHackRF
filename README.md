# SSBHackRF
Turn your HackRF into a SSB Transceiver

Built with Grok.

Enhanced Amateur Radio Capabilities, thanks to PipeWire, Soapy, HackRF, and GNU Radio.

Designed to work with Linux.

Thanks to PipeWire (underrated tool for Ham Radio), this project enables seamless integration between WSJT-X and HackRF, unlocking a wide range of possibilities for ham radio enthusiasts. With Hamlib, you can now:  
Operate WSJT-X and likely others across an impressive frequency range of 1 MHz to 6 GHz, covering bands like 160m, 80m, 60m, 40m, 30m, 20m, 17m, 15m, 12m, 10m, 6m, 2m, 1.25m, 70cm, 30cm, 23cm, 13cm, and 5cm.


With the (poorly) built-in Hamlib server emulation, dynamic switching between RX and TX, along with precise frequency control, is now fully achievable.

Potentially support voice operations alongside digital modes, leveraging the power of Hamlib and Pipewire's versatility.

Key Notes:  
A filter is recommended to minimize spurious emissions and ensure clean signals.

Pipewire on Linux is highly recommended for audio control

Recommended Pipewire configuration (qpwgraph):

![image](https://github.com/user-attachments/assets/9d698a78-4a2e-494e-9633-3647bd068e0b)

To create the null sink with pipewire:

```mkdir -p ~/.config/pipewire/pipewire.conf.d```

drop in 10-null-sink.conf and reboot




