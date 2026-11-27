//! boot-server: Zakuro's windowless boot (crates/zakuro-core/examples/boot.rs), kept running. The ROM and the
//! recompiled library load once; then one command per line on stdin, one reply per line on stdout.
//! docs/harness/SERVER.md (FE Fates harness, owner OK "E" 2026-11-13). MIT, as Zakuro.
//!
//! Same settings as boot.exe (ZAKURO_DATA, ZAKURO_CLOCK, ZAKURO_RECOMPILED, ZAKURO_RASTERIZER, ...), read the same
//! way, and the same per-frame work: the input of the absolute-frame list held for 6 frames from its frame,
//! run_frame, the software keyboard answered, screens and memory dumped only on the frames asked for.
//! Not here: the ZAKURO_INPUT / ZAKURO_SAVE_AT / ZAKURO_LOAD / ZAKURO_DUMP_AT variables (commands replace them),
//! mashing, replay files, rooms, the swap of a library, the end-of-run report.
//!
//! Every reply line starts with "@@zs " (anything else on stdout, e.g. a shader compiler's own print, is not a
//! reply). Commands (tokens apart by single spaces; a path is the rest of the line):
//!   ping                         -> @@zs ok frame F cycles C
//!   input set SPEC | input add SPEC | input clear | input count
//!                                SPEC = "F:BTN[+BTN],..." as ZAKURO_INPUT ("-" = none). The list is absolute-frame
//!                                and survives load: a step never needs the presses again
//!   set timeout MS | set dump_ranges 0xADDR,LEN;... | set dump_dir PATH | set shot_dir PATH
//!   step N [opts] | step to F [opts]   opts: timeout=MS dump_at=F,F shots=F,F
//!                                -> @@zs ok frame F cycles C ms T   |  @@zs err timeout frame F cycles C ms T
//!                                   |  @@zs err outcome Exited frame F cycles C
//!   save slot NAME | save file PATH    (the file is written whole, then renamed into place). As boot.exe's
//!                                ZAKURO_SAVE_AT, a save first writes what the host's GPU drew down into guest memory:
//!                                later guest memory can differ from a run that never saved there (same instructions)
//!   load slot NAME | load file PATH    -> @@zs ok frame F cycles C ms T bytes N
//!   drop slot NAME | slots
//!   peek 0xADDR,LEN[;0xADDR,LEN...]    -> @@zs bin N  then N raw bytes (the ranges one after another)
//!   dump                         the dump_ranges now, as boot.exe names them: dump_dir/zakuro-dump-0xADDR-F.bin
//!   shot                         both screens now (and the right eye in 3D): shot_dir/zakuro-top-F.ppm ...
//!   rando-answer PATH            (FE Fates' in-game randomizer, round 51) the answer the New Game page would give
//!                                (a JSON file); taken at the next mode pick exactly as the page's Start game (Python
//!                                makes the patch hidden, every cell checked, laid or nothing) -> @@zs ok queued
//!   rando-status                 -> @@zs ok run ID|none notices N
//!   audio start | audio save PATH | audio stop
//!                                (round 61) the sound the console played: start drops what was played before and
//!                                records from the next frame; save writes what was recorded since start as a 16-bit
//!                                stereo WAV at zakuro_core::AUDIO_SAMPLE_RATE (whole, then renamed) and keeps
//!                                recording -> @@zs ok frame F cycles C saved N samples rate R; stop ends it. Not
//!                                recording, the server never takes the samples (the core keeps its last second)
//!                                save/load keep the active randomized run with the state (a file gets PATH.rando.json)
//!   quit
use std::collections::{BTreeMap, HashMap};
use std::io::{BufRead, Write};
use std::time::Instant;

use zakuro_core::services::hid::{InputState, PadState};
use zakuro_core::{fates_rando_session, loader, Config, FrameOutcome};

type Press = (PadState, Option<(u16, u16)>);

struct Server {
    system: zakuro_core::System,
    frame: u64,
    inputs: BTreeMap<u64, Vec<Press>>,
    slots: HashMap<String, Vec<u8>>,
    /// the randomized run each slot was saved in (FE Fates)
    slot_runs: HashMap<String, Option<String>>,
    timeout_ms: u64,
    dump_ranges: Vec<(u32, usize)>,
    dump_dir: Option<String>,
    shot_dir: Option<String>,
    typed: String,
    /// round 61: the samples played since `audio start` (None = not recording)
    audio: Option<Vec<[i16; 2]>>,
}

fn main() {
    // logs go to stderr (the client writes them to a file); stdout carries replies only
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("warn,cranelift_jit=warn"))
        .target(env_logger::Target::Stderr)
        .init();
    let mut args = std::env::args().skip(1);
    let Some(path) = args.next() else {
        eprintln!("usage: boot-server <rom>   (then commands on stdin, docs/harness/SERVER.md)");
        std::process::exit(2);
    };
    for refused in ["ZAKURO_PRESENT", "ZAKURO_REPLAY", "ZAKURO_ROOM", "ZAKURO_ROOM_HOST", "ZAKURO_SWAP_AT"] {
        if std::env::var_os(refused).is_some() {
            eprintln!("boot-server: {refused} is not supported here");
            std::process::exit(2);
        }
    }
    // boot.rs's Config, field for field (ZAKURO_PRESENT=direct's device left out: refused above)
    let config = Config {
        new3ds: std::env::var("ZAKURO_NEW3DS").is_ok_and(|v| v == "1"),
        username: std::env::var("ZAKURO_NICK").unwrap_or_else(|_| "Zakuro".into()),
        console_id: std::env::var("ZAKURO_NICK").map_or(0x5A4B_0000_0000_0001, |nick| {
            nick.bytes().fold(0xCBF2_9CE4_8422_2325u64, |hash, byte| (hash ^ byte as u64).wrapping_mul(0x0100_0000_01B3))
        }),
        language: std::env::var("ZAKURO_LANGUAGE")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(zakuro_core::services::cfg::LANGUAGE_ENGLISH),
        recompiled: std::env::var("ZAKURO_RECOMPILED").ok().map(Into::into),
        find_recompiled: std::env::var_os("ZAKURO_FIND_RECOMPILED").is_some(),
        hardware_renderer: std::env::var("ZAKURO_RASTERIZER").is_ok_and(|v| v == "hardware"),
        resolution: std::env::var("ZAKURO_RESOLUTION").ok().and_then(|v| v.parse().ok()).unwrap_or(1),
        update: std::env::var_os("ZAKURO_UPDATE").map(Into::into),
        dlc: std::env::var_os("ZAKURO_DLC").map(|paths| std::env::split_paths(&paths).collect()).unwrap_or_default(),
        data_dir: std::env::var_os("ZAKURO_DATA").map(Into::into),
        clock: std::env::var("ZAKURO_CLOCK").ok().and_then(|v| v.parse().ok()),
        interpolate: std::env::var("ZAKURO_INTERPOLATE").is_ok_and(|v| v == "1"),
        skip_idle_loops: std::env::var("ZAKURO_IDLE").map_or(true, |v| v != "0"),
        slider_3d: std::env::var("ZAKURO_3D").ok().and_then(|v| v.parse().ok()).unwrap_or(0.0),
        // FEF_RANDO_GAME=seal: the in-game randomizer makes and lays Seal of Flames runs
        // (patch 0013; ZAKURO_DATA is then a copy of the Seal profile's data folder)
        fates_rando_game: std::env::var("FEF_RANDO_GAME").ok().filter(|g| !g.is_empty() && g != "fates"),
        ..Config::default()
    };
    let started = Instant::now();
    let mut system = match loader::load(&path, config) {
        Ok(system) => system,
        Err(e) => {
            eprintln!("failed to load {path}: {e}");
            std::process::exit(1);
        }
    };
    // ZAKURO_ENHANCE as boot.rs (the harness never sets it: no enhancement)
    let enhance = std::env::var("ZAKURO_ENHANCE").unwrap_or_default();
    for cheat in system.cheats.iter_mut().filter(|cheat| cheat.builtin && enhance.split(',').any(|name| name.trim() == cheat.name)) {
        cheat.enabled = true;
        eprintln!("enhancement {} on", cheat.name);
    }
    let mut server = Server {
        system,
        frame: 0,
        inputs: BTreeMap::new(),
        slots: HashMap::new(),
        slot_runs: HashMap::new(),
        timeout_ms: 600_000,
        dump_ranges: Vec::new(),
        dump_dir: None,
        shot_dir: None,
        typed: std::env::var("ZAKURO_KEYBOARD").unwrap_or_else(|_| "Zakuro".to_owned()),
        audio: None,
    };
    let stdout = std::io::stdout();
    let mut out = std::io::BufWriter::new(stdout.lock());
    let _ = writeln!(out, "@@zs ready frame 0 cycles {} ms {}", server.system.cpu.cycles, started.elapsed().as_millis());
    let _ = out.flush();
    let stdin = std::io::stdin();
    let mut line = String::new();
    let mut input = stdin.lock();
    loop {
        line.clear();
        match input.read_line(&mut line) {
            Ok(0) | Err(_) => break, // the client went away
            Ok(_) => {}
        }
        let cmd = line.trim_end_matches(['\r', '\n']);
        if cmd.is_empty() {
            continue;
        }
        if cmd == "quit" {
            let _ = writeln!(out, "@@zs ok bye");
            let _ = out.flush();
            break;
        }
        match server.command(cmd) {
            Ok(Reply::Line(text)) => {
                let _ = writeln!(out, "@@zs ok {text}");
            }
            Ok(Reply::Bytes(bytes)) => {
                let _ = writeln!(out, "@@zs bin {}", bytes.len());
                let _ = out.write_all(&bytes);
            }
            Err(text) => {
                let _ = writeln!(out, "@@zs err {}", text.replace('\n', " "));
            }
        }
        let _ = out.flush();
    }
}

enum Reply {
    Line(String),
    Bytes(Vec<u8>),
}

impl Server {
    fn status(&self) -> String {
        format!("frame {} cycles {}", self.frame, self.system.cpu.cycles)
    }

    fn command(&mut self, cmd: &str) -> Result<Reply, String> {
        let (verb, rest) = cmd.split_once(' ').unwrap_or((cmd, ""));
        match verb {
            "ping" => Ok(Reply::Line(self.status())),
            "input" => {
                let (what, spec) = rest.split_once(' ').unwrap_or((rest, ""));
                match what {
                    "clear" => self.inputs.clear(),
                    "set" | "add" => {
                        let presses = parse_input_script(spec)?;
                        if what == "set" {
                            self.inputs.clear();
                        }
                        for (at, buttons, touch) in presses {
                            self.inputs.entry(at).or_default().push((buttons, touch));
                        }
                    }
                    "count" => {}
                    other => return Err(format!("input {other}: set, add, clear or count")),
                }
                Ok(Reply::Line(format!("inputs {}", self.inputs.values().map(Vec::len).sum::<usize>())))
            }
            "set" => {
                let (key, value) = rest.split_once(' ').ok_or("set KEY VALUE")?;
                match key {
                    "timeout" => self.timeout_ms = value.parse().map_err(|_| "set timeout MS")?,
                    "dump_ranges" => self.dump_ranges = parse_ranges(value)?,
                    "dump_dir" => self.dump_dir = Some(value.to_owned()),
                    "shot_dir" => self.shot_dir = Some(value.to_owned()),
                    other => return Err(format!("set {other}: timeout, dump_ranges, dump_dir, or shot_dir")),
                }
                Ok(Reply::Line(format!("set {key}")))
            }
            "step" => self.step(rest),
            "save" => {
                let (kind, name) = rest.split_once(' ').ok_or("save slot NAME | save file PATH")?;
                let started = Instant::now();
                let bytes = self.system.save_state()?;
                let length = bytes.len();
                match kind {
                    "slot" => {
                        self.slots.insert(name.to_owned(), bytes);
                        self.slot_runs.insert(name.to_owned(), fates_rando_session::state_run(&self.system));
                    }
                    "file" => {
                        write_whole(name, &bytes)?;
                        fates_rando_session::write_state_sidecar(&self.system, std::path::Path::new(name))
                            .map_err(|e| format!("could not write {name}.rando.json: {e}"))?;
                    }
                    other => return Err(format!("save {other}: slot or file")),
                }
                Ok(Reply::Line(format!("{} bytes {length} ms {}", self.status(), started.elapsed().as_millis())))
            }
            "load" => {
                let (kind, name) = rest.split_once(' ').ok_or("load slot NAME | load file PATH")?;
                let started = Instant::now();
                // a slot is taken out while the state loads from it (load_state borrows the system), then put back
                let bytes = match kind {
                    "slot" => self.slots.remove(name).ok_or_else(|| format!("no slot {name}"))?,
                    "file" => std::fs::read(name).map_err(|e| format!("could not read {name}: {e}"))?,
                    other => return Err(format!("load {other}: slot or file")),
                };
                let length = bytes.len();
                let loaded = self.system.load_state(&bytes);
                if kind == "slot" {
                    self.slots.insert(name.to_owned(), bytes);
                }
                loaded?;
                match kind {
                    "slot" => {
                        let run = self.slot_runs.get(name).cloned().flatten();
                        fates_rando_session::state_restore(&mut self.system, run.as_deref());
                    }
                    _ => fates_rando_session::read_state_sidecar(&mut self.system, std::path::Path::new(name)),
                }
                self.frame = self.system.frames;
                Ok(Reply::Line(format!("{} ms {} bytes {length}", self.status(), started.elapsed().as_millis())))
            }
            "rando-answer" => {
                let text = std::fs::read_to_string(rest).map_err(|e| format!("could not read {rest}: {e}"))?;
                fates_rando_session::queue_answer(&mut self.system, text);
                Ok(Reply::Line("queued".to_owned()))
            }
            "rando-status" => {
                let run = fates_rando_session::active_run(&self.system).unwrap_or_else(|| "none".to_owned());
                let notices = fates_rando_session::notices(&self.system);
                for n in &notices {
                    eprintln!("fates_rando notice: {n}");
                }
                Ok(Reply::Line(format!("run {run} notices {}", notices.len())))
            }
            "drop" => {
                let (_, name) = rest.split_once(' ').ok_or("drop slot NAME")?;
                self.slots.remove(name).ok_or_else(|| format!("no slot {name}"))?;
                Ok(Reply::Line(format!("dropped {name}")))
            }
            "slots" => {
                let mut names: Vec<&String> = self.slots.keys().collect();
                names.sort();
                Ok(Reply::Line(format!("slots {}", names.iter().map(|n| n.as_str()).collect::<Vec<_>>().join(","))))
            }
            "peek" => {
                let ranges = parse_ranges(rest)?;
                let total: usize = ranges.iter().map(|(_, n)| n).sum();
                if total > 256 << 20 {
                    return Err("peek: at most 256 MiB at once".into());
                }
                let mut bytes = vec![0u8; total];
                let mut at = 0;
                for (addr, len) in ranges {
                    self.system.memory.read_bytes(addr, &mut bytes[at..at + len]);
                    at += len;
                }
                Ok(Reply::Bytes(bytes))
            }
            "dump" => {
                let written = self.dump_now()?;
                Ok(Reply::Line(format!("{} dumped {written}", self.status())))
            }
            "shot" => {
                let written = self.shot_now()?;
                Ok(Reply::Line(format!("{} shot {written}", self.status())))
            }
            "audio" => {
                let (what, path) = rest.split_once(' ').unwrap_or((rest, ""));
                match what {
                    "start" => {
                        let _ = self.system.take_audio(); // what was played before is not recorded
                        self.audio = Some(Vec::new());
                        Ok(Reply::Line(format!("{} recording", self.status())))
                    }
                    "stop" => {
                        self.audio = None;
                        Ok(Reply::Line(format!("{} stopped", self.status())))
                    }
                    "save" if !path.is_empty() => {
                        let samples = self.audio.as_ref().ok_or("audio save: not recording (audio start first)")?;
                        let rate = zakuro_core::AUDIO_SAMPLE_RATE.round() as u32;
                        std::fs::write(format!("{path}.tmp"), wav(samples, rate)).map_err(|e| format!("audio save {path}: {e}"))?;
                        std::fs::rename(format!("{path}.tmp"), path).map_err(|e| format!("audio save {path}: {e}"))?;
                        Ok(Reply::Line(format!("{} saved {} samples rate {rate}", self.status(), samples.len())))
                    }
                    _ => Err("audio start | audio save PATH | audio stop".into()),
                }
            }
            other => Err(format!("unknown command {other}")),
        }
    }

    fn step(&mut self, rest: &str) -> Result<Reply, String> {
        let mut words = rest.split(' ').filter(|w| !w.is_empty());
        let first = words.next().ok_or("step N | step to F")?;
        let target = if first == "to" {
            words.next().and_then(|f| f.parse::<u64>().ok()).ok_or("step to F")?
        } else {
            self.frame + first.parse::<u64>().map_err(|_| "step N | step to F")?
        };
        if target < self.frame {
            return Err(format!("step to {target}: the state is at frame {} already", self.frame));
        }
        let mut timeout = self.timeout_ms;
        let mut dump_at: Vec<u64> = Vec::new();
        let mut shots: Vec<u64> = Vec::new();
        for word in words {
            let (key, value) = word.split_once('=').ok_or_else(|| format!("step option {word}: key=value"))?;
            let frames = || -> Result<Vec<u64>, String> {
                value.split(',').filter(|f| !f.is_empty()).map(|f| f.parse().map_err(|_| format!("bad frame {f}"))).collect()
            };
            match key {
                "timeout" => timeout = value.parse().map_err(|_| "timeout=MS")?,
                "dump_at" => dump_at = frames()?,
                "shots" => shots = frames()?,
                other => return Err(format!("step option {other}: timeout, dump_at or shots")),
            }
        }
        if !dump_at.is_empty() && (self.dump_dir.is_none() || self.dump_ranges.is_empty()) {
            return Err("dump_at needs set dump_dir and set dump_ranges first".into());
        }
        if !shots.is_empty() && self.shot_dir.is_none() {
            return Err("shots needs set shot_dir first".into());
        }
        let started = Instant::now();
        while self.frame < target {
            let frame = self.frame;
            // boot.rs with a non-empty ZAKURO_INPUT: every listed press held from its frame for 6 frames
            let held: Vec<Press> = self.inputs.range(frame.saturating_sub(5)..=frame).flat_map(|(_, p)| p.iter().copied()).collect();
            let buttons = held.iter().fold(PadState::empty(), |all, (buttons, _)| all | *buttons);
            let touch = held.iter().find_map(|(_, touch)| *touch);
            let axis = |plus: PadState, minus: PadState| buttons.contains(plus) as i8 as f32 - buttons.contains(minus) as i8 as f32;
            self.system.set_input(InputState {
                buttons,
                touch,
                circle_x: axis(PadState::CIRCLE_RIGHT, PadState::CIRCLE_LEFT),
                circle_y: axis(PadState::CIRCLE_UP, PadState::CIRCLE_DOWN),
                c_stick_x: axis(PadState::C_STICK_RIGHT, PadState::C_STICK_LEFT),
                c_stick_y: axis(PadState::C_STICK_UP, PadState::C_STICK_DOWN),
                ..InputState::default()
            });
            let outcome = self.system.run_frame();
            if let Some(buffer) = &mut self.audio {
                buffer.extend_from_slice(&self.system.take_audio());
            }
            let executed = frame + 1;
            if let Some(request) = self.system.keyboard_request() {
                let confirm = request.buttons.len() - 1;
                let typed = self.typed.clone();
                self.system.answer_keyboard(&typed, confirm);
            }
            self.frame = executed;
            // boot.rs's ZAKURO_DUMP_AT order: the screens first, then the memory ranges
            if shots.contains(&executed) {
                self.shot_now()?;
            }
            if dump_at.contains(&executed) {
                self.dump_now()?;
            }
            if outcome != FrameOutcome::Completed {
                return Err(format!("outcome {outcome:?} {} ms {}", self.status(), started.elapsed().as_millis()));
            }
            if started.elapsed().as_millis() as u64 > timeout && self.frame < target {
                return Err(format!("timeout {} ms {}", self.status(), started.elapsed().as_millis()));
            }
        }
        Ok(Reply::Line(format!("{} ms {}", self.status(), started.elapsed().as_millis())))
    }

    fn dump_now(&mut self) -> Result<usize, String> {
        let dir = self.dump_dir.clone().ok_or("set dump_dir first")?;
        let frame = self.frame;
        for &(addr, len) in &self.dump_ranges {
            let mut bytes = vec![0u8; len];
            self.system.memory.read_bytes(addr, &mut bytes);
            write_whole(&format!("{dir}/zakuro-dump-0x{addr:08X}-{frame}.bin"), &bytes)?;
        }
        Ok(self.dump_ranges.len())
    }

    fn shot_now(&mut self) -> Result<usize, String> {
        let dir = self.shot_dir.clone().ok_or("set shot_dir first")?;
        let frame = self.frame;
        let mut written = 0;
        if let Some(right) = self.system.read_right_eye_scaled() {
            save_picture(&right, &format!("{dir}/zakuro-top-right-{frame}.ppm"))?;
            written += 1;
        }
        for (screen, name) in [(zakuro_common::Screen::Top, "top"), (zakuro_common::Screen::Bottom, "bottom")] {
            let picture = self.system.read_screen_scaled(screen);
            save_picture(&picture, &format!("{dir}/zakuro-{name}-{frame}.ppm"))?;
            written += 1;
            if self.system.gpu.interpolates() {
                if let Some(own) = self.system.upright_screen(screen, false) {
                    save_picture(&own, &format!("{dir}/zakuro-{name}-gpu-{frame}.ppm"))?;
                }
                if let Some(between) = self.system.upright_screen(screen, true) {
                    save_picture(&between, &format!("{dir}/zakuro-{name}-between-{frame}.ppm"))?;
                }
            }
        }
        Ok(written)
    }
}

/// a file written whole under a temporary name, then renamed into place, so a reader never sees half of it.
fn write_whole(path: &str, bytes: &[u8]) -> Result<(), String> {
    let tmp = format!("{path}.part");
    std::fs::write(&tmp, bytes).map_err(|e| format!("could not write {tmp}: {e}"))?;
    std::fs::rename(&tmp, path).map_err(|e| format!("could not rename {tmp} to {path}: {e}"))
}

fn save_picture((pixels, width, height): &zakuro_core::Screen, path: &str) -> Result<(), String> {
    let mut ppm = format!("P6\n{width} {height}\n255\n").into_bytes();
    for chunk in pixels.as_chunks::<4>().0 {
        ppm.extend_from_slice(&chunk[..3]);
    }
    write_whole(path, &ppm)
}

fn parse_ranges(spec: &str) -> Result<Vec<(u32, usize)>, String> {
    spec.split(';')
        .filter(|r| !r.trim().is_empty())
        .map(|range| {
            let (addr, len) = range.trim().split_once(',').ok_or_else(|| format!("range {range}: 0xADDR,LEN"))?;
            let addr = u32::from_str_radix(addr.trim().trim_start_matches("0x"), 16).map_err(|_| format!("bad address {addr}"))?;
            let len = len.trim().parse::<usize>().map_err(|_| format!("bad length {len}"))?;
            Ok((addr, len))
        })
        .collect()
}

/// boot.rs's parse_input_script, with an error instead of a skipped entry.
fn parse_input_script(spec: &str) -> Result<Vec<(u64, PadState, Option<(u16, u16)>)>, String> {
    if spec.trim() == "-" || spec.trim().is_empty() {
        return Ok(Vec::new());
    }
    spec.split(',')
        .map(|entry| {
            let (frame, buttons) = entry.trim().split_once(':').ok_or_else(|| format!("input {entry}: F:BTN"))?;
            let mut touch = None;
            let mut held = PadState::empty();
            for name in buttons.split('+') {
                if let Some((x, y)) = name.trim().strip_prefix('@').and_then(|at| at.split_once('x')) {
                    touch = Some((x.parse().map_err(|_| format!("bad touch {name}"))?, y.parse().map_err(|_| format!("bad touch {name}"))?));
                    continue;
                }
                held |= match name.trim().to_ascii_uppercase().as_str() {
                    "A" => PadState::A,
                    "B" => PadState::B,
                    "X" => PadState::X,
                    "Y" => PadState::Y,
                    "L" => PadState::L,
                    "R" => PadState::R,
                    "START" => PadState::START,
                    "SELECT" => PadState::SELECT,
                    "UP" => PadState::UP,
                    "DOWN" => PadState::DOWN,
                    "LEFT" => PadState::LEFT,
                    "RIGHT" => PadState::RIGHT,
                    "CUP" => PadState::CIRCLE_UP,
                    "CDOWN" => PadState::CIRCLE_DOWN,
                    "CLEFT" => PadState::CIRCLE_LEFT,
                    "CRIGHT" => PadState::CIRCLE_RIGHT,
                    "CSUP" => PadState::C_STICK_UP,
                    "CSDOWN" => PadState::C_STICK_DOWN,
                    "CSLEFT" => PadState::C_STICK_LEFT,
                    "CSRIGHT" => PadState::C_STICK_RIGHT,
                    "ZL" => PadState::ZL,
                    "ZR" => PadState::ZR,
                    other => return Err(format!("unknown button '{other}'")),
                };
            }
            let frame = frame.trim().parse::<u64>().map_err(|_| format!("bad frame in {entry}"))?;
            Ok((frame, held, touch))
        })
        .collect()
}

/// 16-bit PCM stereo WAV bytes (round 61, `audio save`).
fn wav(samples: &[[i16; 2]], rate: u32) -> Vec<u8> {
    let data_len = (samples.len() * 4) as u32;
    let mut out = Vec::with_capacity(44 + data_len as usize);
    out.extend_from_slice(b"RIFF");
    out.extend_from_slice(&(36 + data_len).to_le_bytes());
    out.extend_from_slice(b"WAVEfmt ");
    out.extend_from_slice(&16u32.to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes()); // PCM
    out.extend_from_slice(&2u16.to_le_bytes()); // stereo
    out.extend_from_slice(&rate.to_le_bytes());
    out.extend_from_slice(&(rate * 4).to_le_bytes());
    out.extend_from_slice(&4u16.to_le_bytes());
    out.extend_from_slice(&16u16.to_le_bytes());
    out.extend_from_slice(b"data");
    out.extend_from_slice(&data_len.to_le_bytes());
    for [l, r] in samples {
        out.extend_from_slice(&l.to_le_bytes());
        out.extend_from_slice(&r.to_le_bytes());
    }
    out
}
