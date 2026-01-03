import pygame

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

class InputBox:
    def __init__(self, x: int, y: int, width: int, height: int, active_color: tuple[int, int, int]=WHITE, inactive_color: tuple[int, int, int]=BLACK, text: str=""):
        self.rect = pygame.Rect(x, y, width, height)
        self.color = inactive_color
        self.active_color = active_color
        self.inactive_color = inactive_color
        self.text = text
        self.text_surface = pygame.font.SysFont("Arial", 32).render(text, True, self.color)
        self.text_limit_reached = False
        self.active = False

    def handle_event(self, event):

        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            if self.rect.collidepoint(mouse_x, mouse_y):
                self.active = True
                self.color = self.active_color
            else:
                if self.active:
                    self.color = self.inactive_color
                    self.active = False

        if event.type == pygame.KEYDOWN:
            if self.active:
                if event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                    self.text_limit_reached = False
                elif event.key == pygame.K_RETURN or event.key == pygame.K_DELETE or event.key == pygame.K_TAB:
                    pass
                else:
                    if not self.text_limit_reached:
                        self.text += event.unicode

    def draw(self, screen: pygame.Surface):
        self.text_surface = pygame.font.SysFont("Arial", 32).render(self.text, True, self.color)
        if self.text_surface.get_width() + 25 >= self.rect.width:
            self.text_limit_reached = True
        screen.blit(self.text_surface, (self.rect.x + 5, self.rect.y + 5))
        pygame.draw.rect(screen, self.color, self.rect, 2)