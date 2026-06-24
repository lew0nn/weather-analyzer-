from datetime import date
from threading import Thread
import tkinter as tk
from tkinter import messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.dates import DateFormatter, MonthLocator
from matplotlib.figure import Figure

from core import MIN_YEAR, analyze_weather_data, create_weather_request, get_weather_data, search_countries, search_country_cities, search_locations


COLORS = {
    "panel": "#ffffff",
    "text": "#1d1d1f",
    "muted": "#5f6368",
    "grid": "#cfd3dc",
}


class RequestWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Weather Data Analyzer")
        self.root.geometry("620x380")
        self.root.minsize(520, 350)

        self.country_var = tk.StringVar()
        self.city_var = tk.StringVar()
        self.year_var = tk.StringVar(value=str(date.today().year))
        self.lookup_status_var = tk.StringVar()
        self.suggestions = {"country": [], "city": [], "location": []}
        self.selected_location = None
        self.lookup_after_id = None
        self.lookup_id = 0
        self.result = None
        self.is_loading = False

        self.build()

    def build(self):
        main = ttk.Frame(self.root, padding=18)
        main.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main)
        header.pack(fill=tk.X)

        ttk.Label(
            header,
            text="Weather Data Analyzer",
            font=("Segoe UI", 22, "bold"),
        ).pack(side=tk.LEFT, anchor="w")

        ttk.Label(
            main,
            text="Choose a country, city, and year to view the weather analysis.",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(3, 0))

        panel = ttk.Frame(main, padding=16)
        panel.pack(fill=tk.BOTH, expand=True, pady=(14, 0))

        self.country_entry = self.add_field(panel, "Country", self.country_var, 0, combobox=True)
        self.city_entry = self.add_field(panel, "City", self.city_var, 1, combobox=True)
        year_entry = self.add_field(panel, "Year", self.year_var, 2, combobox=True)
        year_entry.configure(values=[str(year) for year in range(date.today().year, MIN_YEAR - 1, -1)])

        ttk.Label(
            panel,
            textvariable=self.lookup_status_var,
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
        ).grid(row=3, column=1, sticky="w", pady=(0, 3))

        self.country_entry.bind("<KeyRelease>", lambda event: self.schedule_lookup("country", event))
        self.country_entry.bind("<<ComboboxSelected>>", self.select_country_value)
        self.city_entry.bind("<KeyRelease>", lambda event: self.schedule_lookup("city" if self.country_var.get().strip() else "location", event))
        self.city_entry.bind("<<ComboboxSelected>>", self.select_city_value)
        year_entry.bind("<Return>", lambda event: self.analyze())
        panel.columnconfigure(1, weight=1)

        actions = ttk.Frame(panel)
        actions.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))

        self.analyze_button = ttk.Button(
            actions,
            text="Analyze",
            command=self.analyze,
        )
        self.analyze_button.pack(side=tk.RIGHT)

        self.country_entry.focus_set()

    def add_field(self, parent, label, variable, row, combobox=False):
        ttk.Label(
            parent,
            text=label,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))

        if combobox:
            entry = ttk.Combobox(parent, textvariable=variable, font=("Segoe UI", 11))
        else:
            entry = ttk.Entry(parent, textvariable=variable, font=("Segoe UI", 11))
        entry.grid(row=row, column=1, sticky="ew", pady=6)
        return entry

    def schedule_lookup(self, suggestion_kind, event=None, delay=450):
        if event and event.keysym in ("Up", "Down", "Left", "Right", "Return", "Tab", "Escape"):
            return

        self.selected_location = None
        if self.lookup_after_id is not None:
            self.root.after_cancel(self.lookup_after_id)

        self.lookup_id += 1
        lookup_id = self.lookup_id
        country = self.country_var.get().strip()
        query = country if suggestion_kind == "country" else self.city_var.get().strip()
        if suggestion_kind == "country":
            self.city_var.set("")
            self.city_entry.configure(values=[])
        if suggestion_kind == "city" and not country:
            self.set_combo_values("city", [])
            self.lookup_status_var.set("")
            return
        if len(query) < 2:
            self.set_combo_values(suggestion_kind, [])
            self.lookup_status_var.set("Type at least 2 characters for suggestions.")
            return

        self.lookup_status_var.set("Searching...")
        self.lookup_after_id = self.root.after(delay, lambda: self.lookup_suggestions(lookup_id, suggestion_kind, query))

    def lookup_suggestions(self, lookup_id, suggestion_kind, query):
        self.lookup_after_id = None
        country = self.country_var.get()
        city = self.city_var.get()

        Thread(
            target=self.load_suggestions,
            args=(lookup_id, suggestion_kind, country, city, query),
            daemon=True,
        ).start()

    def load_suggestions(self, lookup_id, suggestion_kind, country, city, query):
        try:
            if suggestion_kind == "country":
                suggestions = search_countries(country)
            elif suggestion_kind == "city":
                suggestions = search_country_cities(country, city)
            else:
                suggestions = search_locations(country, city)
            error = None
        except Exception as exception:
            suggestions = []
            error = str(exception)

        self.root.after(0, lambda: self.apply_suggestions(lookup_id, suggestion_kind, suggestions, error, query))

    def apply_suggestions(self, lookup_id, suggestion_kind, suggestions, error, query):
        if lookup_id != self.lookup_id:
            return

        self.suggestions[suggestion_kind] = suggestions
        self.set_combo_values(suggestion_kind, [suggestion.label for suggestion in suggestions])

        if error:
            self.set_combo_values(suggestion_kind, [])
            self.lookup_status_var.set(f"Suggestions unavailable: {error}")
        elif suggestions:
            self.lookup_status_var.set(f"{len(suggestions)} suggestion{'s' if len(suggestions) != 1 else ''} found.")
        else:
            self.lookup_status_var.set(f'No matches found for "{query}".')

    def set_combo_values(self, suggestion_kind, values):
        entry = self.country_entry if suggestion_kind == "country" else self.city_entry
        entry.configure(values=values)
        if values and self.root.focus_get() == entry:
            entry.after_idle(lambda: entry.event_generate("<Down>"))

    def select_country_value(self, event=None):
        label = self.country_var.get()
        for suggestion in self.suggestions["country"]:
            if suggestion.label == label:
                self.country_var.set(suggestion.name)
                break
        self.city_var.set("")
        self.selected_location = None
        self.city_entry.focus_set()
        self.schedule_lookup("city", delay=0)

    def select_city_value(self, event=None):
        label = self.city_var.get()
        kind = "city" if self.country_var.get().strip() else "location"
        self.selected_location = None
        for suggestion in self.suggestions[kind]:
            if suggestion.label == label:
                if kind == "location":
                    self.selected_location = suggestion
                    self.country_var.set(suggestion.country)
                    self.city_var.set(suggestion.city)
                else:
                    self.selected_location = suggestion
                    self.country_var.set(suggestion.country)
                    self.city_var.set(suggestion.city)
                break

    def analyze(self):
        if self.is_loading:
            return

        self.is_loading = True
        self.analyze_button.configure(state=tk.DISABLED)

        country = self.country_var.get()
        city = self.city_var.get()
        year = self.year_var.get()
        location = self.selected_location

        Thread(
            target=self.load_weather,
            args=(country, city, year, location),
            daemon=True,
        ).start()

    def load_weather(self, country, city, year, location):
        try:
            request = create_weather_request(country, city, year, location=location)
            weather_table = get_weather_data(request)
            error = None
        except Exception as exception:
            request = None
            weather_table = None
            error = str(exception)

        self.root.after(0, lambda: self.finish_weather_load(request, weather_table, error))

    def finish_weather_load(self, request, weather_table, error):
        self.is_loading = False

        if error:
            self.analyze_button.configure(state=tk.NORMAL)
            messagebox.showerror("Weather request failed", error)
            return

        self.result = (request, weather_table)
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.result


class ResultWindow:
    def __init__(self, request, weather_table):
        self.request = request
        self.weather_table = weather_table
        self.summary = analyze_weather_data(weather_table)
        self.canvas = None
        self.chart_index = 0
        self.charts = self.get_chart_specs()

        self.root = tk.Tk()
        self.root.title("Weather Analysis Result")
        self.root.geometry("1050x720")
        self.root.minsize(860, 620)
        self.root.bind("<Left>", lambda event: self.move_chart(-1))
        self.root.bind("<Right>", lambda event: self.move_chart(1))

        self.main = ttk.Frame(self.root, padding=16)
        self.main.pack(fill=tk.BOTH, expand=True)

        self.build_header()
        self.build_summary()
        self.build_chart_panel()
        self.show_chart()

    def build_header(self):
        header = ttk.Frame(self.main)
        header.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            header,
            text="Weather Data Analyzer",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            header,
            text=self.request.title,
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(3, 0))

    def build_summary(self):
        summary_frame = ttk.Frame(self.main)
        summary_frame.pack(fill=tk.X, pady=(0, 10))

        values = [
            ("Average temp", f"{self.summary['Average temperature']:.1f} C"),
            ("Highest temp", f"{self.summary['Highest temperature']:.1f} C"),
            ("Lowest temp", f"{self.summary['Lowest temperature']:.1f} C"),
            ("Temp variation", f"{self.summary['Temperature variation']:.1f} C"),
            ("Total rain", f"{self.summary['Total rain']:.1f} mm"),
            ("Rainy days", f"{self.summary['Rainy days']}"),
        ]
        if "Average wind" in self.summary:
            values.append(("Average wind", f"{self.summary['Average wind']:.1f} km/h"))

        for column, (label, value) in enumerate(values):
            card = ttk.Frame(summary_frame, padding=8)
            card.grid(row=0, column=column, sticky="nsew", padx=4)

            ttk.Label(card, text=label).pack(anchor="w")
            ttk.Label(
                card,
                text=value,
                font=("Segoe UI", 13, "bold"),
            ).pack(anchor="w", pady=(2, 0))

            summary_frame.columnconfigure(column, weight=1)

    def build_chart_panel(self):
        self.chart_panel = ttk.Frame(self.main, padding=12)
        self.chart_panel.pack(fill=tk.BOTH, expand=True)

        nav = ttk.Frame(self.chart_panel)
        nav.pack(fill=tk.X, pady=(0, 8))

        previous_button = ttk.Button(
            nav,
            text="<",
            command=lambda: self.move_chart(-1),
            width=4,
        )
        previous_button.pack(side=tk.LEFT)

        title_area = ttk.Frame(nav)
        title_area.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        self.chart_title_var = tk.StringVar()
        self.chart_counter_var = tk.StringVar()
        ttk.Label(
            title_area,
            textvariable=self.chart_title_var,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(title_area, textvariable=self.chart_counter_var).pack(anchor="w")

        next_button = ttk.Button(
            nav,
            text=">",
            command=lambda: self.move_chart(1),
            width=4,
        )
        next_button.pack(side=tk.RIGHT)

        self.chart_frame = ttk.Frame(self.chart_panel)
        self.chart_frame.pack(fill=tk.BOTH, expand=True)

    def move_chart(self, step):
        self.chart_index = (self.chart_index + step) % len(self.charts)
        self.show_chart()

    def show_chart(self):
        if self.canvas is not None:
            self.canvas.get_tk_widget().destroy()

        chart_spec = self.charts[self.chart_index]
        self.chart_title_var.set(chart_spec["title"])
        self.chart_counter_var.set(f"Chart {self.chart_index + 1} of {len(self.charts)}")

        colors = COLORS
        figure = Figure(figsize=(9.5, 4.7), dpi=100)
        figure.patch.set_facecolor(colors["panel"])

        chart = figure.add_subplot(111)
        chart_spec["draw"](chart)
        self.style_chart(chart, chart_spec)

        figure.autofmt_xdate()
        figure.tight_layout()

        self.canvas = FigureCanvasTkAgg(figure, master=self.chart_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def get_chart_specs(self):
        specs = []
        columns = set(self.weather_table.columns)

        def add(title, x_axis, y_axis, draw, date_axis=False, legend=False):
            specs.append({
                "title": title,
                "x_axis": x_axis,
                "y_axis": y_axis,
                "draw": draw,
                "date_axis": date_axis,
                "legend": legend,
            })

        if {
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
        }.issubset(columns):
            add(
                "Daily Temperature",
                "Months",
                "Temperature in Celsius",
                self.draw_temperature_lines,
                date_axis=True,
                legend=True,
            )
            add(
                "Daily Temperature Range",
                "Months",
                "Temperature difference in Celsius",
                self.draw_temperature_range,
                date_axis=True,
            )
            add(
                "Monthly Average Temperature",
                "Months",
                "Average temperature in Celsius",
                self.draw_monthly_temperature,
            )

        if "precipitation_sum" in columns:
            add(
                "Daily Rain and Snow",
                "Months",
                "Precipitation amount in millimeters",
                self.draw_precipitation,
                date_axis=True,
            )

        if {"temperature_2m_mean", "precipitation_sum"}.issubset(columns):
            add(
                "Temperature vs Precipitation",
                "Average daily temperature in Celsius",
                "Daily precipitation in millimeters",
                self.draw_temperature_vs_rain,
            )

        if "wind_speed_10m_max" in columns:
            add(
                "Daily Wind Speed",
                "Months",
                "Wind speed in kilometers per hour",
                self.draw_wind,
                date_axis=True,
            )

        return specs

    def draw_temperature_lines(self, chart):
        chart.plot(self.weather_table["time"], self.weather_table["temperature_2m_max"], label="Maximum", color="#ef4444", linewidth=1.5)
        chart.plot(self.weather_table["time"], self.weather_table["temperature_2m_mean"], label="Average", color="#8b5cf6", linewidth=1.8)
        chart.plot(self.weather_table["time"], self.weather_table["temperature_2m_min"], label="Minimum", color="#06b6d4", linewidth=1.5)
        chart.plot(self.weather_table["time"], self.weather_table["temperature_smooth"], label="7-day avg", color="#111827", linewidth=2)

    def draw_temperature_range(self, chart):
        chart.plot(self.weather_table["time"], self.weather_table["temperature_range"], color="#f59e0b", linewidth=1.8)

    def draw_monthly_temperature(self, chart):
        monthly_temperature = (
            self.weather_table
            .assign(month=self.weather_table["time"].dt.month)
            .groupby("month")["temperature_2m_mean"]
            .mean()
        )
        chart.bar(monthly_temperature.index, monthly_temperature.values, color="#14b8a6")
        month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        months = list(monthly_temperature.index)
        chart.set_xticks(months)
        chart.set_xticklabels([month_labels[month - 1] for month in months])

    def draw_precipitation(self, chart):
        chart.bar(self.weather_table["time"], self.weather_table["precipitation_sum"], color="#2f80ed")

    def draw_temperature_vs_rain(self, chart):
        chart.scatter(
            self.weather_table["temperature_2m_mean"],
            self.weather_table["precipitation_sum"],
            color="#a855f7",
            alpha=0.7,
            edgecolors="none",
        )

    def draw_wind(self, chart):
        chart.plot(self.weather_table["time"], self.weather_table["wind_speed_10m_max"], color="#22c55e", linewidth=1.8)

    def style_chart(self, chart, chart_spec):
        colors = COLORS
        chart.set_facecolor(colors["panel"])
        chart.set_title(chart_spec["title"], color=colors["text"], pad=12)
        chart.set_xlabel(chart_spec["x_axis"], color=colors["text"])
        chart.set_ylabel(chart_spec["y_axis"], color=colors["text"])
        chart.tick_params(colors=colors["muted"])
        chart.grid(True, alpha=0.3, color=colors["grid"])
        if chart_spec.get("date_axis"):
            self.format_date_axis(chart)

        for spine in chart.spines.values():
            spine.set_color(colors["grid"])

        if chart_spec["legend"]:
            legend = chart.legend()
            legend.get_frame().set_facecolor(colors["panel"])
            legend.get_frame().set_edgecolor(colors["grid"])
            for text in legend.get_texts():
                text.set_color(colors["text"])

    def format_date_axis(self, chart):
        colors = COLORS
        month_locator = MonthLocator()
        chart.xaxis.set_major_locator(month_locator)
        chart.xaxis.set_major_formatter(DateFormatter("%b"))

        start = self.weather_table["time"].min().replace(day=1)
        end = self.weather_table["time"].max()
        for month_start in self.month_starts(start, end):
            chart.axvline(month_start, color=colors["grid"], linewidth=0.7, alpha=0.45)

    def month_starts(self, start, end):
        current = start
        while current <= end:
            yield current
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    def run(self):
        self.root.mainloop()
