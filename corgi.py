from flask import Flask, Markup, render_template, request
from geopy import distance, Point
from random import random

import folium
import networkx as nx
import osmnx as ox

def generate_points(point_n, point_sep, home):
    """
    Generates a list of 'n' points that plot an appropriate route.
    """

    # Generate placeholders and geopy functions
    points = [home]
    last_point = Point(home)
    d = distance.distance(meters=point_sep)

    # Create points
    for i in range(point_n):
        while True:
            # A new point is defined by the chosen seperation distance and
            # a random bearing from the last point
            new_point = d.destination(point=last_point, bearing=random()*360)

            # The point will only be used if it isn't too far from the start
            if distance.distance(new_point, home).meters <= (point_n-i)*point_sep:
                x,y,_ = new_point
                points.append([x,y])
                last_point = new_point
                break

    return points

def process_with_OSM(points, snap_to_OSM):
    """
    This function does some post-processing using Open Street Map data to affix
    points to ways, and to determine and measure the shortest routes between
    them.
    """

    def _get_network(points):
        """
        This function gets the network from OSMs servers.
        """

        # First we calculate the bounding-box required
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        sw = Point([min(lats), min(lons)])
        ne = Point([max(lats), max(lons)])
        # We add a border of 1km around the bounding-box to capture edge ways
        d = distance.distance(meters=1000)
        sw = d.destination(point=sw, bearing=180+45)
        ne = d.destination(point=ne, bearing=45)

        # Download graph from OSM
        graph = ox.graph_from_bbox(
            ne[0], sw[0], ne[1], sw[1],
            simplify=False,
            network_type="walk"
        )

        return graph

    def _snap_points_to_ways(graph, points):
        """
        Snap points to the nearest OSM ways, then modify the points.
        """

        # Uses OSMnx's get_nearest_node functionality
        # We could use the get_nearest_edge method but then we need to work out
        # how to get the coordinates from the correct point on the edge
        nodes = []
        for point_i, point in enumerate(points):
            nn = ox.get_nearest_node(graph, point)
            nodes.append(nn)
            coords = [graph.nodes[nn]['y'], graph.nodes[nn]['x']]
            points[point_i] = coords

        return points, nodes

    def _calculate_route(graph, nodes):
        """
        Function determines the shortest route between all points.
        """

        route = []
        nodes.append(nodes[0])
        for node_i in range(len(nodes)-1):
            # Uses NetworkX's shortest_path which defaults to dijkstra method
            path = nx.shortest_path(graph, nodes[node_i], nodes[node_i+1])
            # Convert back from node IDs to coordinates
            for node in path:
                coords = [graph.nodes[node]['y'], graph.nodes[node]['x']]
                route.append(coords)

        return route

    if snap_to_OSM:
        graph = _get_network(points)
        points, nodes = _snap_points_to_ways(graph, points)
        route = _calculate_route(graph, nodes)
        return points, route

    else:
        return points, []

def generate_map(points, route, snap_to_OSM):
    """
    Function generates a folium map with markers at each tuple given in points.
    """

    def _centroid(points):
        """
        Function returns the centroid of a list of points.
        """
        x, y = 0, 0
        for point in points:
            x += point[0]
            y += point[1]
        x /= len(points)
        y /= len(points)

        return [x, y]

    # Centroid of points is used as map centre (saves paper/screen real-estate)
    centroid = _centroid(points)
    m = folium.Map(
        location=centroid,
        #tiles="Stamen Terrain",
        zoom_start=14
    )

    # Route between points is marked on the map
    if snap_to_OSM:
        fg_route = folium.FeatureGroup(name="Route")
        folium.vector_layers.PolyLine(
            route,
            tooltip="Route",
            smooth_factor = 0,
            color="purple",
            opacity=0.5
        ).add_to(fg_route)
        fg_route.add_to(m)

    # Show LayerControl on map
    folium.LayerControl().add_to(m)

    # Home point is marked on map
    folium.Marker(
        points[0],
        tooltip="Home",
        icon=folium.Icon(
            color='green',
            icon='home'
        )
    ).add_to(m)

    # Other points are marked on map
    for point_i, point in enumerate(points[1:]):
        folium.Marker(
            point,
            tooltip=f"Point: {point_i+1}",
        ).add_to(m)

    return m

app = Flask(__name__)
@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Function is run when the index page is GET or POST requested
    """

    attributes = {'lat': 50.730275, 'lon': -3.518295, 'n': 5, 'sep': 1000, 'snap': 'on'}

    # Process changes to attributes given in POST request
    if request.method == 'POST':
        for key in attributes:
            if request.form.get(key) != '':
                if key == 'snap':
                    attributes[key] = request.form.get(key)
                elif (key == 'n' or key == 'sep'):
                    attributes[key] = int(request.form.get(key))
                else:
                    attributes[key] = float(request.form.get(key))

    # Continue with loading map
    points = generate_points(attributes['n'], attributes['sep'], [attributes['lat'], attributes['lon']])
    points, route = process_with_OSM(points, (attributes['snap'] == 'on'))
    m = generate_map(points, route, (attributes['snap'] == 'on'))

    # Save string represetation for adding to template
    htmlmap = m._repr_html_()

    # Add map to template and render
    return render_template('index.html', lat=attributes['lat'], lon=attributes['lon'], n=attributes['n'], sep=attributes['sep'], snap=attributes['snap'], htmlmap=Markup(htmlmap))

if __name__ == "__main__":
    app.run(debug=True)
