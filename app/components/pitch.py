import plotly.graph_objects as go


def pitch(players, lineup, captain, vice):
    p = players.set_index("id")
    fig = go.Figure()
    for position, y in ((1, 12), (2, 33), (3, 58), (4, 82)):
        ids = [i for i in lineup if p.at[i, "element_type"] == position]
        xs = [(j + 1) * 100 / (len(ids) + 1) for j in range(len(ids))]
        labels = [
            f"{p.at[i, 'name']}{' (C)' if i == captain else ' (V)' if i == vice else ''}"
            for i in ids
        ]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=[y] * len(ids),
                mode="markers+text",
                text=labels,
                textposition="top center",
                marker={"size": 24, "color": "#f1f5f9"},
                hovertext=[f"{p.at[i, 'club']} · £{p.at[i, 'price']:.1f}m" for i in ids],
                hoverinfo="text",
            )
        )
    fig.add_shape(type="rect", x0=0, x1=100, y0=0, y1=100, line_color="white")
    fig.add_shape(type="line", x0=0, x1=100, y0=50, y1=50, line_color="white")
    fig.add_shape(type="circle", x0=40, x1=60, y0=40, y1=60, line_color="white")
    fig.update_layout(
        height=520,
        plot_bgcolor="#176b45",
        paper_bgcolor="#176b45",
        font_color="white",
        showlegend=False,
        margin={"l": 15, "r": 15, "t": 25, "b": 15},
        xaxis={"range": [-2, 102], "visible": False},
        yaxis={"range": [-2, 102], "visible": False},
    )
    return fig
