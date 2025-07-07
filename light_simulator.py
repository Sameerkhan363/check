# light_simulator.py
import tkinter as tk
import threading

class LightSimulator:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("IoT Light Simulation")
        self.canvas = tk.Canvas(self.window, width=200, height=200)
        self.canvas.pack()
        self.light = self.canvas.create_oval(50, 50, 150, 150, fill="grey")
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        self.running = True
        threading.Thread(target=self.window.mainloop, daemon=True).start()

    def on_close(self):
        self.running = False
        self.window.destroy()

    def set_light(self, color):
        if not self.running:
            return
        self.canvas.itemconfig(self.light, fill=color)

    def green(self):
        print("🟢 GREEN light ON")
        self.set_light("green")

    def red(self):
        print("🔴 RED light ON")
        self.set_light("red")

    def off(self):
        print("⚫ Light OFF")
        self.set_light("grey")
