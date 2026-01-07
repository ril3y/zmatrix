# ZMatrix TODO

## Multi-Receiver Support
**Priority:** Low (single card setup works fine)

When using multiple 5A-75B boards on the same network:

- [ ] Implement discovery response parsing to get each receiver's unique Controller Address
- [ ] Add `--receiver-addr` CLI flag to target specific receiver
- [ ] Add `--list-receivers` to show all discovered boards
- [ ] Support sending different pixel regions to different receivers

**Technical notes (from RE):**
- Controller Address: bytes 0x0E-0x1D (16 bytes)
- All zeros = broadcast to all receivers
- Each receiver has factory-set unique address
- Discovery (0x07) returns CReceiverInfo with address

## Future Enhancements

- [ ] Implement discovery response parsing (get firmware version, model, etc.)
- [ ] Add gamma table support (packet type 0x76)
- [ ] Add void line configuration (packet type 0x1F)
- [ ] Framebuffer device integration (`/dev/fb0` style)
- [ ] Performance optimization (sendqueue batching like WinPcap)
- [ ] Add `--parse-rcvbp` flag to load config from LEDVISION file

## Hardware Testing Needed

- [ ] Verify config packets with Wireshark capture
- [ ] Test different scan modes (4/8/16/32)
- [ ] Test color order with different panel ICs
- [ ] Measure actual refresh rate / bandwidth
