import trimesh
import numpy as np
import os
import random

import scipy
import binvox_rw
import matplotlib.pyplot as plt
import copy

from typing import List, Tuple

random.seed(777)

class PreprocessConfig:    
    OBJ_FORMAT = ".obj"
    BINVOX_FORMAT = ".binvox"
    
    BINVOX_RESOLUTION = 128

    ROTATION_MAX = 360
    ROTATION_INTERVAL = 36

    X = (1, 0, 0)
    Y = (0, 1, 0)
    Z = (0, 0, 1)

    DATA_BASE_DIR = "data"
    DATA_ORIGINAL_DIR = "original"
    DATA_PREPROCESSED_DIR = "preprocessed"

    DATA_ORIGINAL_DIR_MERGED = os.path.join(DATA_BASE_DIR, DATA_ORIGINAL_DIR)
    DATA_PREPROCESSED_DIR_MERGED = os.path.join(DATA_BASE_DIR, DATA_PREPROCESSED_DIR)


class Utils:
    @staticmethod
    def normalize_mesh(mesh: trimesh.Trimesh) -> None:
        """Normalize to 0 ~ 1 values the given mesh

        Args:
            mesh (trimesh.Trimesh): Given mesh to normalize
        """

        verts = mesh.vertices
        centers = np.mean(verts, axis=0)
        verts = verts - centers
        length = np.max(np.linalg.norm(verts, 2, axis=1))
        verts = verts * (1. / length)
        
        mesh.vertices = verts
    
    @staticmethod
    def get_rotated_mesh(
        mesh: trimesh.Trimesh, angle: float, axis: Tuple[int] = PreprocessConfig.Z
    ) -> trimesh.Trimesh:
        """Return the rotated mesh by the given mesh and angle

        Args:
            mesh (trimesh.Trimesh): Given mesh
            angle (float): Angle to rotate
            axis (Tuple[int], optional): Axis to rotate. Defaults to PreprocessConfig.Z.

        Returns:
            trimesh.Trimesh: Rotated mesh
        """

        rotation_matrix = trimesh.transformations.rotation_matrix(angle, axis)
        rotated_mesh = copy.deepcopy(mesh)
        rotated_mesh.path = mesh.path
        rotated_mesh.apply_transform(rotation_matrix)
        
        return rotated_mesh

    @staticmethod
    def get_mirrored_mesh(
        mesh: trimesh.Trimesh, point: Tuple[float] = None, normal: Tuple[float] = None
    ) -> trimesh.Trimesh:
        """Return the mirrored mesh by the given mesh, normal and point

        Args:
            mesh (trimesh.Trimesh): Mesh to mirror
            point (Tuple[float], optional): Base point to mirror. Defaults to None.
            normal (Tuple[float], optional): Base vextor to mirror. Defaults to None.

        Returns:
            trimesh.Trimesh: Mirrored mesh
        """
        
        if point is None:
            point = mesh.centroid

        if normal is None:
            normal = PreprocessConfig.X

        mirroring_transform = trimesh.transformations.reflection_matrix(point=point, normal=normal)
        mirrored_mesh = copy.deepcopy(mesh)
        mirrored_mesh.path = mesh.path
        mirrored_mesh.apply_transform(mirroring_transform)
        
        return mirrored_mesh
    
    @staticmethod
    def get_binvox_model(path: str) -> binvox_rw.Voxels:
        """Get binvox data from the path

        Args:
            path (str): binvox data path

        Returns:
            binvox_rw.Voxels: model
        """

        with open(path, 'rb') as f:
            model = binvox_rw.read_as_3d_array(f)

        return model
        
    @staticmethod
    def load_mesh(path: str, normalize: bool = False, map_y_to_z: bool = False) -> trimesh.Trimesh:
        """Load mesh data from .obj file

        Args:
            path (str): Path to load
            normalize (bool, optional): Whether normalizing mesh. Defaults to False.
            map_y_to_z (bool, optional): Change axes (y to z, z to y). Defaults to False.

        Returns:
            trimesh.Trimesh: Loaded mesh
        """
        
        mesh = trimesh.load(path)
        
        if isinstance(mesh, trimesh.Scene):
            geo_list = []
            for g in mesh.geometry.values():
                geo_list.append(g)
            mesh = trimesh.util.concatenate(geo_list)

        mesh.fix_normals(multibody=True)

        if normalize:
            Utils.normalize_mesh(mesh)
            
        if map_y_to_z:
            mesh.vertices[:, [1, 2]] = mesh.vertices[:, [2, 1]]

        mesh.path = path

        return mesh

    @staticmethod
    def mesh_to_binvox(
        mesh: trimesh.Trimesh,
        save_path: str,
        resolution: int, 
    ) -> None:
        """Convert mesh that is shaped .obj format to .binvox

        Args:
            mesh (trimesh.Trimesh): Given mesh
            save_path (str): Path to save
            resolution (int): Binary voxel grid resolution
        """

        data_name = mesh.path.split("\\")[-1]
        merged_save_path = os.path.join(save_path, data_name)
        mesh.export(merged_save_path)
                    
        command = f"binvox -cb -e -d {resolution} {merged_save_path}"
        os.system(command)
        
        for file_name in os.listdir(save_path):
            if not file_name.endswith(".binvox"):
                os.remove(os.path.join(save_path, file_name))
        
    @staticmethod
    def plot_binvox(
        data_list: List[np.ndarray], 
        plot_voxels: bool = False, 
        downsample_rate: float = 1.0,
        title: str = "",
        figsize: Tuple[int] = None,
    ) -> None:
        """Plot .binvox data

        Args:
            data_list (List[np.ndarray]): Given binvox data list
            plot_voxels (bool, optional): Whether plotting voxel or scatter. Defaults to False.
            downsample_rate (float, optional): Resolution for only plotting. Defaults to 1.0.
            title (str, optional): Title to plot. Defaults to "".
        """

        data_list_length = len(data_list)
        data_list_divider = 10
        row = max(1, int(np.ceil(data_list_length / data_list_divider)))
        
        if figsize is None:
            figsize = (data_list_length * 2, data_list_length / 3)
        
        figure = plt.figure(figsize=figsize)
        figure.suptitle(title)

        color = "blue"

        for n in range(1, data_list_length + 1):
            ax = figure.add_subplot(row, data_list_divider, n, projection="3d")
            
            data = data_list[n - 1]
            
            x, y, z = data.nonzero()

            if plot_voxels:
                data = scipy.ndimage.zoom(data, downsample_rate, order=0)
                ax.voxels(data, facecolors=color)
            else:
                ax.scatter(x, y, z, c=color)

        ax.set_aspect("equal")
        figure.tight_layout()

        plt.show()

class Preprocessor(Utils):
    def __init__(
        self, 
        use_to_rotate: bool = False,
        use_to_mirror: bool = False,
        use_to_overwrite: bool = False,
        use_to_plot: bool = False,
        plot_voxels: bool = False,
        binvox_resolution: int = PreprocessConfig.BINVOX_RESOLUTION, 
        rotation_interval: float = PreprocessConfig.ROTATION_INTERVAL,
        rotation_max: float = PreprocessConfig.ROTATION_MAX
        
    ):  
        self.use_to_rotate = use_to_rotate
        self.use_to_mirror = use_to_mirror
        self.use_to_overwrite = use_to_overwrite
        self.use_to_plot = use_to_plot
        
        self.plot_voxels = plot_voxels

        self.binvox_resolution = binvox_resolution
        self.rotation_interval = rotation_interval
        self.rotation_max = rotation_max
        
        assert self.rotation_interval > 0, "The input`rotation_interval` is not bigger than 0."

    
    def preprocess(self) -> None:
        """Main function for preprocessing data
        """
        
        for data_name in os.listdir(PreprocessConfig.DATA_ORIGINAL_DIR_MERGED):
            
            each_save_dir = os.path.join(PreprocessConfig.DATA_PREPROCESSED_DIR_MERGED, data_name)
            if not os.path.isdir(each_save_dir):
                os.mkdir(each_save_dir)
            
            each_obj_data_path = os.path.join(
                PreprocessConfig.DATA_ORIGINAL_DIR_MERGED,
                data_name, 
                data_name + PreprocessConfig.OBJ_FORMAT
            )

            if self.use_to_overwrite:
                for file_name in os.listdir(each_save_dir):
                    if file_name.endswith(PreprocessConfig.BINVOX_FORMAT):
                        os.remove(os.path.join(each_save_dir, file_name))

            mesh_to_preprocess: List[trimesh.Trimesh]
            mesh_to_preprocess = []
            
            mesh = self.load_mesh(path=each_obj_data_path, normalize=True, map_y_to_z=True)
            mesh_to_preprocess.append(mesh)
            
            if self.use_to_mirror:
                mirrored_mesh = self.get_mirrored_mesh(mesh=mesh)
                mesh_to_preprocess.append(mirrored_mesh)

            for each_mesh_to_preprocess in mesh_to_preprocess:
                self.mesh_to_binvox(
                    mesh=each_mesh_to_preprocess,
                    save_path=each_save_dir, 
                    resolution=self.binvox_resolution, 
                )
                
                if self.use_to_rotate:
                    rotation_degree = self.rotation_interval

                    while True:
                        
                        rotated_mesh = self.get_rotated_mesh(
                            mesh=each_mesh_to_preprocess, angle=np.radians(rotation_degree)
                        )
                        
                        rotation_degree += self.rotation_interval

                        self.mesh_to_binvox(
                            mesh=rotated_mesh,
                            save_path=each_save_dir, 
                            resolution=self.binvox_resolution, 
                        )
                        
                        if (
                            rotation_degree >= PreprocessConfig.ROTATION_MAX
                            or np.isclose(rotation_degree, PreprocessConfig.ROTATION_MAX)
                        ):
                            break

            data_list: List[np.ndarray]
            data_list = []
                        
            for each_data in os.listdir(each_save_dir):
                if each_data.endswith(".binvox"):
                    each_binvox_data_path = os.path.join(each_save_dir, each_data)
                    model = self.get_binvox_model(each_binvox_data_path)

                    data_list.append(model.data)

            if self.use_to_plot:
                self.plot_binvox(
                    data_list=random.choices(data_list, k=7), 
                    plot_voxels=self.plot_voxels, 
                    title=f"{data_name} plotted randomly"
                )