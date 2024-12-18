import time
import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from typing import Callable, List, Union


def runtime_calculator(func: Callable) -> Callable:
    """A decorator function for measuring the runtime of another function.

    Args:
        func (Callable): Function to measure

    Returns:
        Callable: Decorator
    """

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        runtime = end_time - start_time
        print(f"The function {func.__name__} took {runtime} seconds to run.")
        return result

    return wrapper


def vectorize_polygon_from_array(binary_grid: np.ndarray) -> np.ndarray:
    """Convert a binary grid-shaped polygon represented as a 2D array of 1s and 0s into a vectorized Numpy array.

    Args:
        binary_grid (np.ndarray): 2D Numpy array representing the binary image.

    Raises:
        ValueError: occurs if there are no contours

    Returns:
        np.ndarray: Numpy array representing the vertices of the largest polygon.
    """

    image = np.uint8(binary_grid * 255)

    contours, _ = cv2.findContours(image, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        raise ValueError("No contours found in the array.")

    polygon_contour = max(contours, key=cv2.contourArea)

    epsilon = 0.01 * cv2.arcLength(polygon_contour, True)
    approx_polygon = cv2.approxPolyDP(polygon_contour, epsilon, True)

    return np.array(approx_polygon).squeeze()


def get_binary_grid_shaped_polygon(coordinates: np.ndarray, canvas_size: np.ndarray) -> np.ndarray:
    """Convert a given polygon coordinates to the binary grid-shaped polygon

    Args:
        coordinates (np.ndarray): polygon coordinates

    Returns:
        np.ndarray: binary grid
    """

    binary_grid_shaped_polygon = np.zeros(canvas_size, np.uint8)
    cv2.fillPoly(binary_grid_shaped_polygon, [coordinates], 255)

    binary_grid_shaped_polygon = (binary_grid_shaped_polygon == 255).astype(np.uint8)

    return binary_grid_shaped_polygon


def plot_binary_grids(
    binary_grids: List[np.ndarray], colormap: Union[List[str], str] = None, save_path: str = None
) -> None:
    """visualize multiple binary grids in a row

    Args:
        binary_grids (List[np.ndarray]): list of binary grids
        colormap (Union[List[str], str], optional): colormap to use for displaying the binary grids. Defaults to None.
    """

    n = len(binary_grids)
    fig, axs = plt.subplots(1, n, figsize=(n * 5, 5))

    # Handle colormap
    matplotlib_colormap = "Greys"
    if colormap is not None:
        if isinstance(colormap, list):
            matplotlib_colormap = mcolors.ListedColormap(colormap)
        elif isinstance(colormap, str):
            matplotlib_colormap = colormap

    for i, grid in enumerate(binary_grids):
        if n == 1:
            ax = axs
        else:
            ax = axs[i]
        ax.imshow(grid, cmap=matplotlib_colormap)
        ax.axis("off")

    if save_path is not None:
        fig.savefig(save_path)

    plt.show()


def plot_losses(losses_g, losses_d, figsize=(10, 5), plot_avg_line=False, save_path=None):
    """Visualizes the generator and discriminator losses,
    draws a dashed line for average losses and annotates them."""

    if save_path is not None and 1 in (len(losses_d), len(losses_g)):
        plt.figure(figsize=figsize)
        plt.savefig(save_path)
        plt.close()
        return

    if len(losses_g) <= 1:
        return

    plt.figure(figsize=figsize)
    plt.title(f"Generator and Discriminator Losses At {len(losses_g)} Epoch")

    # Plot the losses
    plt.plot(losses_g, label="Generator Loss", alpha=0.6)
    plt.plot(losses_d, label="Discriminator Loss", alpha=0.6)

    if plot_avg_line:
        # Calculate and plot the average loss for generator
        avg_loss_g = sum(losses_g) / len(losses_g)
        plt.axhline(avg_loss_g, linestyle="--", color="red")
        plt.annotate(
            f"Avg Loss G: {avg_loss_g:.6f}",
            xy=(len(losses_g) - 1, avg_loss_g),
            xytext=(len(losses_g) - 1.5, avg_loss_g + 0.1),
            color="red",
        )

        # Calculate and plot the average loss for discriminator
        avg_loss_d = sum(losses_d) / len(losses_d)
        plt.axhline(avg_loss_d, linestyle="--", color="green")
        plt.annotate(
            f"Avg Loss D: {avg_loss_d:.6f}",
            xy=(len(losses_d) - 1, avg_loss_d),
            xytext=(len(losses_d) - 1.5, avg_loss_d - 0.1),
            color="green",
        )

    # Get the latest loss values
    latest_loss_g = losses_g[-1]
    latest_loss_d = losses_d[-1]

    # Annotate the latest loss values on the plot
    plt.annotate(
        f"Loss G: {latest_loss_g:.6f}",
        xy=(len(losses_g) - 1, latest_loss_g),
        xytext=(len(losses_g) - 1.5, latest_loss_g + 0.1),
    )

    plt.annotate(
        f"Loss D: {latest_loss_d:.6f}",
        xy=(len(losses_d) - 1, latest_loss_d),
        xytext=(len(losses_d) - 1.5, latest_loss_d - 0.1),
    )

    plt.xlabel("Epochs")
    plt.ylabel("Loss")
    plt.legend()
    plt.grid(True, which="both", linestyle="--", linewidth=0.5)

    if save_path is not None:
        plt.savefig(save_path)

    plt.show()


def calculate_polygon_angles(polygon_vertices: np.ndarray) -> List[float]:
    """_summary_

    Args:
        polygon_vertices (np.ndarray): _description_

    Returns:
        List[float]: _description_
    """

    polygon_angles = []

    for vi in range(len(polygon_vertices)):
        p0 = polygon_vertices[(vi - 1) % len(polygon_vertices)]
        p1 = polygon_vertices[vi]
        p2 = polygon_vertices[(vi + 1) % len(polygon_vertices)]

        d1 = p0 - p1
        d2 = p2 - p1

        dot_prod = np.dot(d1, d2)
        norm_prod = np.linalg.norm(d1) * np.linalg.norm(d2)

        cos_angle = dot_prod / norm_prod
        angle = np.arccos(cos_angle) * (180.0 / np.pi)

        polygon_angles.append(angle)

    return polygon_angles
