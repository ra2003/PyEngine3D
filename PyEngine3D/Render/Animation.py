import copy

from PyEngine3D.Common import logger
from PyEngine3D.Utilities import *


class Animation:
    def __init__(self, name, index, skeleton, animation_data):
        self.name = name
        self.index = index
        self.skeleton = skeleton
        self.frame_count = 0
        self.frame_times = []
        self.animation_length = 0.0
        self.nodes = []  # order by bone index
        for i, animation_node_data in enumerate(animation_data):
            animation_node = AnimationNode(self.skeleton.bones[i], animation_node_data)
            frame_count = len(animation_node.frame_times)
            if self.frame_count < frame_count:
                self.frame_count = frame_count
                self.frame_times = copy.copy(animation_node.frame_times)
            self.nodes.append(animation_node)
        if 0 < self.frame_count:
            self.animation_length = max(self.frame_times)
        self.last_frame = 0.0
        self.current_frame = 0
        self.animation_time = 0.0

        # just update animation transforms
        self.animation_transforms = np.array([Matrix4() for i in range(len(self.nodes))], dtype=np.float32)
        self.get_animation_transforms(0.0)

    def get_time_to_frame(self, deltaTime):
        if 1 < self.frame_count:
            current_time = self.animation_time + deltaTime

            while True:
                if self.frame_times[self.current_frame] <= current_time <= self.frame_times[self.current_frame + 1]:
                    break
                self.current_frame = (self.current_frame + 1) % (self.frame_count - 1)

            frame_time = self.frame_times[self.current_frame]
            next_frame_time = self.frame_times[self.current_frame + 1]
            ratio = (current_time - frame_time) / (next_frame_time - frame_time)
            return float(self.current_frame) + ratio
        return 0.0

    def get_animation_transforms(self, frame=0.0):
        if self.last_frame == frame:
            return self.animation_transforms
        else:
            for i, node in enumerate(self.nodes):
                self.animation_transforms[i][...] = node.get_transform(frame)
            return self.animation_transforms


class AnimationNode:
    def __init__(self, bone, animation_node_data):
        self.name = animation_node_data.get('name', '')
        self.bone = bone
        self.target = animation_node_data.get('target', '')  # bone name
        self.frame_times = animation_node_data.get('times', [])
        # self.transforms = animation_node_data.get('transforms', [])
        self.locations = animation_node_data.get('locations', [])
        self.rotations = animation_node_data.get('rotations', [])
        self.scales = animation_node_data.get('scales', [])
        self.interpoations = animation_node_data.get('interpoations', [])
        self.in_tangents = animation_node_data.get('in_tangents', [])
        self.out_tangents = animation_node_data.get('out_tangents', [])

        self.frame_count = len(self.frame_times)
        self.last_frame = -1.0
        self.transform = MATRIX4_IDENTITY.copy()
        # just update transform
        self.get_transform(0.0)

    def get_transform(self, frame=0.0):
        if self.last_frame == frame or self.frame_count == 0:
            return self.transform
        else:
            self.last_frame = frame

            rate = frame - int(frame)
            frame = int(frame) % self.frame_count
            next_frame = (frame + 1) % self.frame_count
            
            set_identity_matrix(self.transform)
            if frame < self.frame_count:
                rotation = slerp(self.rotations[frame], self.rotations[next_frame], rate)
                # rotation = normalize(lerp(self.rotations[frame], self.rotations[next_frame], rate))
                location = lerp(self.locations[frame], self.locations[next_frame], rate)
                scale = lerp(self.scales[frame], self.scales[next_frame], rate)
                quaternion_to_matrix(rotation, self.transform)
                matrix_scale(self.transform, *scale)
                self.transform[3, 0:3] = location
            self.transform[...] = np.dot(self.bone.inv_bind_matrix, self.transform)
            return self.transform
