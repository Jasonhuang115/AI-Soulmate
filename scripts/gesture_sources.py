"""Unique Motifect BVH sources for catalog keys (phase 2+3)."""

from __future__ import annotations

# pack/file.bvh under data/mixamo/unpacked/{pack}/BVH/
GESTURE_SOURCES: dict[str, str] = {
    # phase 2
    "nod": "daily/nod_yes.bvh",
    "shake_head": "daily/shake_head_no.bvh",
    "bow": "daily/bow_greeting.bvh",
    "sit": "daily/sit_down_chair.bvh",
    "lean_in": "emotes/explain_wide_gesture.bvh",
    "stretch": "daily/stretch_morning.bvh",
    "point": "emotes/point_at_opponent.bvh",
    "laugh": "emotes/laugh_body.bvh",
    "tilt": "loco/idle_looking_around.bvh",
    "cover_mouth": "emotes/cover_face_embarrassed.bvh",
    "thumbs_up": "emotes/thumbs_up.bvh",
    "shrug": "emotes/shrug_i_dont_know.bvh",
    "dance": "emotes/dance_simple_groove.bvh",
    "walk": "loco/walk_forward.bvh",
    "yes": "emotes/fist_pump_victory.bvh",
    "no": "emotes/no_way_hands_out.bvh",
    "cheer": "emotes/cheer_arms_raised.bvh",
    "crouch": "loco/crouch_idle.bvh",
    "stand": "loco/idle_neutral.bvh",
    "turn_left": "loco/turn_left_90.bvh",
    "turn_right": "loco/turn_right_90.bvh",
    "hands_on_hips": "emotes/arms_crossed_defiant.bvh",
    "salute": "emotes/salute_military.bvh",
    "blow_kiss": "daily/hug_greeting.bvh",
    "facepalm": "emotes/facepalm.bvh",
    "come_here": "emotes/taunt_come_here.bvh",
    "go_away": "emotes/thumbs_down.bvh",
    "celebrate": "emotes/jump_for_joy.bvh",
    "cry": "emotes/slump_defeated.bvh",
    "confused": "emotes/hold_up_wait.bvh",
    "bored": "daily/sit_idle_slouched.bvh",
    "excited": "emotes/excited_spin.bvh",
    "pray": "emotes/bow_deep_respect.bvh",
    "kneel": "daily/tie_shoelaces.bvh",
    "lie_down": "daily/lie_down_on_bed.bvh",
    "handshake": "daily/shake_hands.bvh",
    "peek": "loco/tiptoe_walk.bvh",
    "wait": "loco/idle_alert.bvh",
    # phase 3
    "run": "loco/run_sprint.bvh",
    "jog": "loco/run_jog.bvh",
    "sit_idle": "daily/sit_idle_upright.bvh",
    "stand_up": "daily/stand_up_from_chair.bvh",
    "sit_down": "emotes/sit_and_wave_goodbye.bvh",
    "kick": "emotes/stomp_frustrated.bvh",
    "punch": "emotes/challenge_stance.bvh",
    "dodge": "loco/sidestep_dodge.bvh",
    "roll": "loco/roll_forward.bvh",
    "climb": "loco/climb_ledge.bvh",
    "wave_both": "daily/wave_hello.bvh",
    "clap_slow": "emotes/clap_enthusiastic.bvh",
    "dance_hiphop": "emotes/dance_arm_wave.bvh",
    "dance_silly": "loco/jump_standing.bvh",
    "yoga": "daily/get_up_from_floor.bvh",
    "jump_joy": "loco/jump_running.bvh",
    "head_scratch": "daily/comb_hair.bvh",
    "check_watch": "daily/check_phone_standing.bvh",
    "talk": "emotes/talk_animate_hands.bvh",
    "talk_angry": "emotes/taunt_throat_slash.bvh",
    "talk_happy": "daily/present_to_audience.bvh",
    "drink": "daily/drink_from_cup.bvh",
    "eat": "daily/eat_with_fork.bvh",
    "sneeze": "emotes/shrink_away_scared.bvh",
    "cough": "daily/brush_teeth.bvh",
    "yawn": "daily/yawn_and_stretch.bvh",
    "stretch_arm": "daily/put_on_jacket.bvh",
    "neck_roll": "emotes/think_chin_stroke.bvh",
    "step_back": "loco/walk_backward.bvh",
    "step_forward": "loco/walk_confident.bvh",
    "look_up": "daily/write_on_whiteboard.bvh",
    "look_down": "daily/pick_up_object_floor.bvh",
    "point_up": "daily/take_photo_with_phone.bvh",
    "point_down": "daily/put_down_object_table.bvh",
    "happy_walk": "loco/start_sprint.bvh",
    "sad_walk": "loco/walk_tired.bvh",
    "bow_deep": "emotes/taunt_mock_bow.bvh",
    "curtsy": "loco/crouch_rise_up.bvh",
    "hold_item": "daily/carry_box_two_hands.bvh",
    "push_up": "daily/get_up_from_bed.bvh",
    "macarena": "loco/direction_change_sharp.bvh",
    "robot": "loco/back_to_wall.bvh",
    "moonwalk": "loco/run_backward.bvh",
    "samba": "loco/run_strafe_left.bvh",
    "count": "daily/type_on_keyboard.bvh",
    "thinking_walk": "loco/walk_cautious.bvh",
    "hip_sway": "loco/idle_relaxed_weight_shift.bvh",
    "idle_happy": "daily/carry_grocery_bags.bvh",
    "idle_sad": "loco/stumble_recover.bvh",
    "spin": "loco/turn_180.bvh",
}


def assert_unique_sources() -> None:
    # idle_happy currently shares wave_hello with wave_both — fix below if so.
    used: dict[str, str] = {}
    dupes: list[str] = []
    for name, source in GESTURE_SOURCES.items():
        if source in used:
            dupes.append(f"{name} and {used[source]} -> {source}")
        else:
            used[source] = name
    if dupes:
        raise ValueError("duplicate gesture sources: " + "; ".join(dupes))
