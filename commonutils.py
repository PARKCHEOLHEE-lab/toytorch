import os
import imageio


def create_animation_gif(
    images_directory: str,
    save_path: str,
    format: str = "png",
    loop: int = 0,
    duration: int = 1,
) -> None:
    """Create an animated GIF from a directory of images.

    Args:
        images_directory (str): Directory path containing images.
        save_path (str): File path to save the generated GIF.
        format (str, optional): Format of the image files (default is "png").
        loop (int, optional): Number of loops for the GIF (0 for infinite looping, default is 0).
        duration (int, optional): Duration (in milliseconds) of each frame (default is 1).
    """

    files = sorted(os.listdir(images_directory), key=lambda x: int(x.split("-")[-1].split(".")[0]))
    files = [os.path.abspath(os.path.join(images_directory, file)) for file in files if file.endswith(format)]

    images_data = []
    for file in files:
        data = imageio.imread(file)
        images_data.append(data)

    imageio.mimwrite(save_path, images_data, format=".gif", duration=duration, loop=loop)
