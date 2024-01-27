import os
import torch
import torch.nn as nn
import numpy as np

from typing import List, Tuple
from lirGAN.config import ModelConfig
from lirGAN.data.data_creator import DataCreator
from lirGAN.data import utils
from torch.utils.data import Dataset, DataLoader
from torch.nn.modules.loss import _Loss
from IPython.display import clear_output


class LirDataset(Dataset, ModelConfig):
    def __init__(self, data_path: str = None, slicer: int = np.inf):
        self.lir_dataset: List[torch.Tensor]
        self.lir_dataset = self._get_lir_dataset(
            data_path=self.DATA_PATH if data_path is None else data_path, slicer=slicer
        )

    def __len__(self) -> int:
        return len(self.lir_dataset)

    def __getitem__(self, index) -> Tuple[torch.Tensor]:
        input_polygon, target_lir = self.lir_dataset[index]

        return input_polygon.unsqueeze(dim=0).to(self.DEVICE), target_lir.unsqueeze(dim=0).to(self.DEVICE)

    def _get_lir_dataset(self, data_path: str, slicer: int) -> List[torch.Tensor]:
        """Load the lir dataset

        Args:
            data_path (str): path to load data

        Returns:
            List[torch.Tensor]: Each tensor is (2, 500, 500)-shaped tensor.
                                The first one is the input polygon and the second one is ground-truth rectangle
        """

        lir_dataset: List[torch.Tensor]
        lir_dataset = []

        for file_name in os.listdir(data_path):
            lir_data_path = os.path.join(data_path, file_name)
            lir_dataset.append(torch.tensor(np.load(lir_data_path), dtype=torch.float))

        if slicer < np.inf:
            return lir_dataset[:slicer]

        return lir_dataset


class LirGeometricLoss(nn.Module):
    def __init__(
        self,
        bce_weight: float = 1.0,
        diou_weight: float = 1.0,
        feasibility_weight: float = 1.0,
    ):
        super().__init__()

        self.bce_weight = bce_weight
        self.diou_weight = diou_weight
        self.feasibility_weight = feasibility_weight

        self.bce_loss_function = nn.BCEWithLogitsLoss()

    @staticmethod
    def compute_diou_loss(generated_lir: torch.Tensor, target_lir: torch.Tensor, diou_weight: float) -> torch.Tensor:
        """compute the distance-IoU loss

        Args:
            generated_lir (torch.Tensor):  generated rectangle
            target_lir (torch.Tensor): target rectangle
            diou_weight (float): weight to multiply in the diou loss

        Returns:
            torch.Tensor: diou loss
        """

        intersection = torch.logical_and(generated_lir, target_lir).float()
        union = torch.logical_or(generated_lir, target_lir).float()
        iou_score = torch.sum(intersection) / torch.sum(union)

        generated_lir_centroid = torch.nonzero(generated_lir).float().mean(dim=0)
        target_lir_centroid = torch.nonzero(target_lir).float().mean(dim=0)

        distance = torch.norm(generated_lir_centroid - target_lir_centroid)

        diagonal = torch.norm(torch.tensor(generated_lir.shape).float())

        normalized_distance = (distance / diagonal) ** 2

        diou_loss = 1 - (iou_score - normalized_distance)

        return diou_loss * diou_weight

    @staticmethod
    def compute_feasibility_loss(
        input_polygon: torch.Tensor, generated_lir: torch.Tensor, feasibility_weight: float
    ) -> torch.Tensor:
        """compute the feasibility loss that checks the generated rectangle is within the input polygon

        Args:
            input_polygon (torch.Tensor): input polygon boundary to predict
            generated_lir (torch.Tensor): generated rectangle
            feasibility_weight (float): weight to multiply in the feasibility loss

        Returns:
            torch.Tensor: feasibility loss
        """

        infeasibility_mask = (generated_lir == 1) & (input_polygon != 1)
        feasibility_loss = infeasibility_mask.sum().float() / input_polygon.sum().float()

        return feasibility_loss * feasibility_weight

    def forward(
        self, input_polygons: torch.Tensor, generated_lirs: torch.Tensor, target_lirs: torch.Tensor
    ) -> torch.Tensor:
        """compute total loss

        Args:
            input_polygons (torch.Tensor): input polygon boundaries to predict
            generated_lirs (torch.Tensor): generated rectangles
            target_lirs (torch.Tensor): target rectangles

        Returns:
            torch.Tensor: loss merged with bce, diou, feasibility
        """

        total_loss = 0
        for generated_lir, target_lir, input_polygon in zip(generated_lirs, target_lirs, input_polygons):
            bce_loss = self.bce_loss_function(generated_lir, target_lir)

            diou_loss = LirGeometricLoss.compute_diou_loss(generated_lir, target_lir, self.diou_weight)
            feasibility_loss = LirGeometricLoss.compute_feasibility_loss(
                input_polygon, generated_lir, self.feasibility_weight
            )

            loss = bce_loss + diou_loss + feasibility_loss

            total_loss += loss

        return total_loss


class WeightsInitializer:
    @staticmethod
    def initialize_weights_xavier(m):
        if isinstance(m, (nn.Conv3d, nn.ConvTranspose3d)):
            nn.init.xavier_normal_(m.weight)
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.BatchNorm3d):
            nn.init.constant_(m.weight, 1)
            nn.init.constant_(m.bias, 0)

    @staticmethod
    def initialize_weights_he(m):
        if isinstance(m, (nn.Conv3d, nn.ConvTranspose3d)):
            nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)
        elif isinstance(m, nn.BatchNorm3d):
            nn.init.constant_(m.weight, 1)
            nn.init.constant_(m.bias, 0)


class LirGenerator(nn.Module, ModelConfig):
    def __init__(self):
        super().__init__()

        self.main = nn.Sequential(
            nn.Conv2d(1, 64, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(True),
            nn.Conv2d(64, 32, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(True),
            nn.Conv2d(32, 16, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU(True),
            nn.ConvTranspose2d(16, 32, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(True),
            nn.ConvTranspose2d(32, 64, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(True),
            nn.ConvTranspose2d(64, 1, kernel_size=8, stride=2, padding=1, bias=False),
            nn.Sigmoid(),
        )

        self.main.to(self.DEVICE)

    def forward(self, input_polygon):
        return self.main(input_polygon)


class LirDiscriminator(nn.Module, ModelConfig):
    def __init__(self):
        super().__init__()

        self.main = nn.Sequential(
            nn.Conv2d(1, 64, kernel_size=4, stride=2, padding=1, bias=False),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(64, 128, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(128, 256, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(256, 512, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(512),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(512, 512, kernel_size=4, stride=2, padding=1, bias=False),
            nn.BatchNorm2d(512),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(512, 1, kernel_size=15, stride=15, padding=0, bias=False),
            nn.Sigmoid(),
        )

        self.main.to(self.DEVICE)

    def forward(self, generated_lir):
        return self.main(generated_lir).view(-1, 1).squeeze(1)


class LirGanTrainer(ModelConfig, WeightsInitializer):
    def __init__(
        self,
        lir_generator: LirGenerator,
        lir_discriminator: LirDiscriminator,
        lir_dataloader: DataLoader,
        lir_geometric_loss_function: LirGeometricLoss = None,
        lir_discriminator_loss_function: _Loss = nn.BCEWithLogitsLoss(),
        initial_weights_key: str = None,
    ):
        self.lir_generator = lir_generator
        self.lir_discriminator = lir_discriminator
        self.lir_dataloader = lir_dataloader
        self.lir_geometric_loss_function = lir_geometric_loss_function
        self.lir_discriminator_loss_function = lir_discriminator_loss_function
        self.initial_weights_key = initial_weights_key

        self.lir_generator_optimizer, self.lir_discriminator_optimizer = self._get_optimizers(
            self.lir_generator, self.lir_discriminator, self.LEARNING_RATE, self.BETAS
        )

        if self.initial_weights_key is not None:
            self._set_initial_weights(self.lir_generator, self.lir_discriminator, self.initial_weights_key)

    def _get_optimizers(
        self,
        lir_generator: LirGenerator,
        lir_discriminator: LirDiscriminator,
        learning_rate: float,
        betas: Tuple[float],
    ) -> Tuple[torch.optim.Optimizer, torch.optim.Optimizer]:
        """Set and return optimizers

        Args:
            lir_generator (LirGenerator): generator model
            lir_discriminator (LirDiscriminator): discriminator model

        Returns:
            Tuple[torch.optim.Optimizer, torch.optim.Optimizer]: Optimizers
        """

        lir_generator_optimizer = torch.optim.Adam(lir_generator.parameters(), lr=learning_rate, betas=betas)
        lir_discriminator_optimizer = torch.optim.Adam(lir_discriminator.parameters(), lr=learning_rate, betas=betas)

        return lir_generator_optimizer, lir_discriminator_optimizer

    def _set_initial_weights(
        self, lir_generator: LirGenerator, lir_discriminator: LirDiscriminator, initial_weights_key: str
    ) -> None:
        """_summary_

        Args:
            lir_generator (LirGenerator): _description_
            lir_discriminator (LirDiscriminator): _description_
            initial_weights_key (str): _description_
        """

        if initial_weights_key == self.XAVIER:
            lir_generator.apply(self.initialize_weights_xavier)
            lir_discriminator.apply(self.initialize_weights_xavier)
        elif initial_weights_key == self.HE:
            lir_generator.apply(self.initialize_weights_he)
            lir_discriminator.apply(self.initialize_weights_he)

    def _train_lir_discriminator(self, input_polygons: torch.Tensor, target_lirs: torch.Tensor):
        """_summary_

        Args:
            input_polygon (torch.Tensor): _description_
            target_lir (torch.Tensor): _description_

        Returns:
            _type_: _description_
        """

        generated_lir = self.lir_generator(input_polygons)

        real_d = self.lir_discriminator(target_lirs)
        fake_d = self.lir_discriminator(generated_lir)

        loss_real_d = self.lir_discriminator_loss_function(real_d, torch.ones_like(real_d))
        loss_fake_d = self.lir_discriminator_loss_function(fake_d, torch.zeros_like(fake_d))

        loss_d = loss_real_d + loss_fake_d

        self.lir_discriminator_optimizer.zero_grad()
        loss_d.backward()
        self.lir_discriminator_optimizer.step()

        return loss_d

    def _train_lir_generator(self, input_polygons: torch.Tensor, target_lirs: torch.Tensor):
        generated_lir = self.lir_generator(input_polygons)

        fake_d = self.lir_discriminator(generated_lir)

        adversarial_loss = self.lir_discriminator_loss_function(fake_d, torch.ones_like(fake_d))
        geometric_loss = 0
        if self.lir_geometric_loss_function is not None:
            geometric_loss = self.lir_geometric_loss_function(input_polygons, generated_lir, target_lirs)

        loss_g = adversarial_loss + geometric_loss

        self.lir_generator_optimizer.zero_grad()
        loss_g.backward()
        self.lir_generator_optimizer.step()

        return loss_g

    def evaluate(self, batch_size_to_evaulate: int):
        self.lir_generator.eval()
        self.lir_discriminator.eval()

        with torch.no_grad():
            binary_grids = []

            data_creator = DataCreator(creation_count=None)
            for _ in range(batch_size_to_evaulate):
                random_coordinates = data_creator._get_random_coordinates(
                    vertices_count_min=data_creator.random_vertices_count_min,
                    vertices_count_max=data_creator.random_vertices_count_max,
                )

                binary_grid_shaped_polygon = utils.get_binary_grid_shaped_polygon(
                    random_coordinates.astype(np.int32), data_creator.canvas_size
                )

                random_input_polygon = (
                    torch.tensor(binary_grid_shaped_polygon, dtype=torch.float)
                    .unsqueeze(dim=0)
                    .unsqueeze(dim=0)
                    .to(self.DEVICE)
                )

                generated_lir = self.lir_generator(random_input_polygon) > 0.5

                _ = binary_grid_shaped_polygon + generated_lir.squeeze().detach().cpu().numpy().astype(int)
                binary_grids.append(binary_grid_shaped_polygon)

            utils.visualize_binary_grids(binary_grids)

        self.lir_generator.train()
        self.lir_discriminator.train()

    def train(self):
        """Main function to train models"""

        losses_g = []
        losses_d = []

        for epoch in range(1, self.EPOCHS + 1):
            if epoch % self.LOG_INTERVAL == 0:
                clear_output(wait=True)

            losses_g_per_epoch = []
            losses_d_per_epoch = []

            for input_polygons, target_lirs in self.lir_dataloader:
                loss_d = self._train_lir_discriminator(input_polygons, target_lirs)
                loss_g = self._train_lir_generator(input_polygons, target_lirs)
                losses_g_per_epoch.append(loss_g.item())
                losses_d_per_epoch.append(loss_d.item())

            avg_loss_g = np.mean(losses_g_per_epoch)
            avg_loss_d = np.mean(losses_d_per_epoch)
            losses_g.append(avg_loss_g)
            losses_d.append(avg_loss_d)

            if epoch % self.LOG_INTERVAL == 0:
                if len(self.lir_dataloader) == 1:
                    # FIXME: Functionalizing the following codes
                    self.lir_generator.eval()
                    self.lir_discriminator.eval()
                    with torch.no_grad():
                        print(f"epoch: {epoch}/{self.EPOCHS}")
                        input_polygon = input_polygons.squeeze().detach().cpu().numpy()
                        target_lir = target_lirs.squeeze().detach().cpu().numpy()
                        ground_truth = input_polygon + target_lir

                        generated_lir = (
                            (self.lir_generator(input_polygons) > 0.5).squeeze().detach().cpu().numpy().astype(int)
                        )

                        generated = input_polygon + generated_lir

                        utils.visualize_binary_grids([ground_truth, generated])

                    self.lir_generator.train()
                    self.lir_discriminator.train()

                    utils.plot_losses(losses_g=losses_g, losses_d=losses_d)

                else:
                    self.evaluate(self.BATCH_SIZE_TO_EVALUATE)
