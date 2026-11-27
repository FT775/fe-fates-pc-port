#!/usr/bin/env python3
"""List Vulkan physical devices through libvulkan.so.1 (ctypes). No vulkan-tools, no sudo, no downloads.

Prints one line per device and a summary line `vulkan: devices real=N cpu=N other=N`.
Exit 0 only if at least one real (integrated or discrete GPU, not llvmpipe/lavapipe) device exists.
A CPU device (llvmpipe/lavapipe, deviceType CPU) is never a pass (risk 20).
"""
import ctypes
import sys

TYPES = {0: "OTHER", 1: "INTEGRATED_GPU", 2: "DISCRETE_GPU", 3: "VIRTUAL_GPU", 4: "CPU"}


class InstanceCreateInfo(ctypes.Structure):
    _fields_ = [("sType", ctypes.c_uint32), ("pNext", ctypes.c_void_p), ("flags", ctypes.c_uint32),
                ("pApplicationInfo", ctypes.c_void_p), ("enabledLayerCount", ctypes.c_uint32),
                ("ppEnabledLayerNames", ctypes.c_void_p), ("enabledExtensionCount", ctypes.c_uint32),
                ("ppEnabledExtensionNames", ctypes.c_void_p)]


def main() -> int:
    try:
        vk = ctypes.CDLL("libvulkan.so.1")
    except OSError as e:
        print(f"vulkan: no loader ({e})")
        print("vulkan: devices real=0 cpu=0 other=0")
        return 1
    inst = ctypes.c_void_p()
    info = InstanceCreateInfo(sType=1)  # VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO
    rc = vk.vkCreateInstance(ctypes.byref(info), None, ctypes.byref(inst))
    if rc != 0:
        print(f"vulkan: vkCreateInstance failed ({rc})")
        print("vulkan: devices real=0 cpu=0 other=0")
        return 1
    n = ctypes.c_uint32(0)
    vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), None)
    devs = (ctypes.c_void_p * max(n.value, 1))()
    vk.vkEnumeratePhysicalDevices(inst, ctypes.byref(n), devs)
    real = cpu = other = 0
    for i in range(n.value):
        buf = ctypes.create_string_buffer(8192)  # VkPhysicalDeviceProperties is < 1 KiB
        vk.vkGetPhysicalDeviceProperties(ctypes.c_void_p(devs[i]), buf)
        api, drv, vendor, device, dtype = (int.from_bytes(buf.raw[o:o + 4], "little") for o in range(0, 20, 4))
        name = buf.raw[20:276].split(b"\0", 1)[0].decode("utf-8", "replace")
        soft = dtype == 4 or any(s in name.lower() for s in ("llvmpipe", "lavapipe"))
        kind = "cpu" if soft else ("real" if dtype in (1, 2) else "other")
        real += kind == "real"
        cpu += kind == "cpu"
        other += kind == "other"
        print(f"vulkan device {i}: {name} type={TYPES.get(dtype, dtype)} vendor=0x{vendor:04x} "
              f"api={api >> 22}.{(api >> 12) & 0x3ff}.{api & 0xfff} -> {kind}")
    vk.vkDestroyInstance(inst, None)
    print(f"vulkan: devices real={real} cpu={cpu} other={other}")
    return 0 if real else 1


if __name__ == "__main__":
    sys.exit(main())
