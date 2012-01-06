# -*- coding: utf-8 -*-
"""
BGP

eBGP
====
eBGP is configured automatically, if there is an edge in the physical graph between two nodes that belong to different Autonomous Systems:

``if asn(s) != asn(t) for s,t in edges``

iBGP
====

    * Peer column refers to connections at the same level (eg 2->2)
    * Parent column refers to connections to level above (eg 1->2)
    * There are no child connections (eg 3->2)
    * as_cluster is the entire AS

    l2_cluster can be manually specified. If not specified, it defaults to being a PoP.
    If no PoPs specified, it defaults to being the AS.

    l3_cluster defaults to asn if not set: we connect the l2 rr to all l3 rrs in the same AS.

    Three types of ibgp connection:

    * *up* to a server
    * *down* to a client
    * *over* to a peer

    .. note::

        If the network only has level 1 route-reflectors, then the connections are labelled as *peer*


    The below tables show the matching attributes to use.
    
    1-level:

    =========   ==========          ==========
    Level       Peer                Parent
    ---------   ----------          ----------
    1           asn                 None      
    =========   ==========          ==========

    2-level:

    =========   ==========          ==========
    Level       Peer                Parent
    ---------   ----------          ----------
    1           None                l2_cluster
    2           asn                 None
    =========   ==========          ==========

    3-level:

    =========   =============       ===========
    Level       Peer                Parent
    ---------   -------------       -----------
    1           None                l2_cluster
    2           l2_cluster          l3_cluster
    3           asn                 None 
    =========   =============       ===========

"""
__author__ = "\n".join(['Simon Knight'])
#    Copyright (C) 2009-2011 by Simon Knight, Hung Nguyen

__all__ = ['ebgp_routers', 'get_ebgp_graph',
           'ibgp_routers', 'get_ibgp_graph',
           'initialise_bgp']

import networkx as nx
import pprint
import AutoNetkit as ank
import logging
LOG = logging.getLogger("ANK")

def ebgp_edges(network):
    """
    Returns eBGP edges once configured from initialise_ebgp

    """
    return ( (s,t) for s,t in network.g_session.edges()
            if network.asn(s) != network.asn(t))

def ibgp_edges(network):
    """ iBGP edges in network 

    >>> network = ank.example_single_as()
    >>> initialise_ibgp(network)
    >>> list(sorted(ibgp_edges(network)))
    [('1a', '1b'), ('1a', '1c'), ('1a', '1d'), ('1b', '1a'), ('1b', '1c'), ('1b', '1d'), ('1c', '1a'), ('1c', '1b'), ('1c', '1d'), ('1d', '1a'), ('1d', '1b'), ('1d', '1c')]
    """
    return ( (s,t) for s,t in network.g_session.edges()
            if network.asn(s) == network.asn(t))

def configure_ibgp_rr(network):
    """Configures route-reflection properties based on work in (NEED CITE).

    Note: this currently needs ibgp_level to be set globally for route-reflection to work.
    Future work will implement on a per-AS basis.
    """
    LOG.debug("Configuring iBGP route reflectors")
# Add all nodes from physical graph
#TODO: if no 
    g_session = nx.DiGraph()
    g_session.add_nodes_from(network.graph)

    def match_same_l2_cluster(u,v):
        return ( network.graph.node[u]['ibgp_l2_cluster'] == network.graph.node[u]['ibgp_l2_cluster'] != "" )

    def match_same_l3_cluster(u,v):
        return ( network.graph.node[u]['ibgp_l3_cluster'] == network.graph.node[u]['ibgp_l3_cluster'] != "" )

    def level(u):
        return int(network.graph.node[u]['ibgp_level'])

    for my_as in ank.get_as_graphs(network):
        #TODO: for neatness, look at redefining the above functions inside here setting my_as as network
        asn = my_as.name
        nodes_with_level_set = sum(1 for n in my_as if network.graph.node[n].get('ibgp_level'))
        if nodes_with_level_set != len(my_as):
            if nodes_with_level_set != 0:
                LOG.info("Only %s/%s nodes in AS%s have ibgp_level set" % (nodes_with_level_set,
                    len(my_as), asn))
                LOG.info("Setting ibgp_level to 1 for nodes in AS%s" % asn)
            # none set, user probably doesn't care for this AS, do full-mesh
            LOG.debug("Setting ibgp_level to 1 for nodes in AS%s" % asn)
            for node in my_as:
                network.graph.node[node]['ibgp_level'] = 1

        max_ibgp_level = max(level(n) for n in my_as)

        if max_ibgp_level >= 2:
            print "max level >= 2 is", max_ibgp_level
            for node, data in my_as.nodes(data=True):
                if not data.get("ibgp_l2_cluster"):
                    # due to boolean evaluation will set in order from left to right
                    network.graph.node[node]['ibgp_l2_cluster'] = data.get("pop") or asn

                if max_ibgp_level == 3:
                    if not data.get("ibgp_l3_cluster"):
                        # due to boolean evaluation will set in order from left to right
                        network.graph.node[node]['ibgp_l3_cluster'] = asn
# Now connect
        edges_to_add = []
# List of edges for easier iteration (rather than doing each time)
        as_edges = [ (s,t) for s in my_as for t in my_as if s != t]

        if max_ibgp_level == 1:
            #1           asn                 None      
            edges_to_add += [(s, t, {'rr_dir': 'peer'}) for (s,t) in as_edges]
        else:
            same_l2_cluster_edges = [ (s,t) for (s,t) in as_edges if match_same_l2_cluster(s,t)]
# This is the same for both level 2 and level 3 networks
            #1           None                l2_cluster
            edges_to_add += [(s,t, {'rr_dir': 'up'}) for (s,t) in same_l2_cluster_edges
                    if level(s) == 1 and level(t) == 2]
            edges_to_add += [(s,t, {'rr_dir': 'down'}) for (s,t) in same_l2_cluster_edges
                    if level(s) == 2 and level(t) == 1]

        if max_ibgp_level == 2:
            #1           None                l2_cluster
# done above
            #2           asn                 None
# Full-mesh at level 2
            edges_to_add += [(s, t, {'rr_dir': 'peer'}) for (s,t) in same_l2_cluster_edges 
                    if level(s) == level(t) == 2]
        elif max_ibgp_level == 3:
            same_l3_cluster_edges = [ (s,t) for (s,t) in as_edges if match_same_l3_cluster(s,t)]
            #1           None                l2_cluster
# done above
            #2           l2_cluster          l3_cluster
            edges_to_add += [(s,t, {'rr_dir': 'peer'}) for (s,t) in same_l2_cluster_edges
                    if level(s) == level(t) == 2]
            edges_to_add += [(s,t, {'rr_dir': 'up'}) for (s,t) in same_l2_cluster_edges
                    if level(s) == 2 and level(t) == 3]
            edges_to_add += [(s,t, {'rr_dir': 'down'}) for (s,t) in same_l2_cluster_edges
                    if level(s) == 3 and level(t) == 2]
            #3           asn                 None 
            edges_to_add += [(s, t, {'rr_dir': 'peer'}) for (s,t) in same_l3_cluster_edges 
                    if level(s) == level(t) == 3]

        print "edges to add", edges_to_add
        g_session.add_edges_from(edges_to_add)

    network.g_session = g_session
    #pprint.pprint(g_session.nodes(data=True))
    #pprint.pprint(g_session.edges(data=True))
    for s,t,data in g_session.edges(data=True):
        print network.label(s), network.label(t), data['rr_dir']

    """ Make groups
    max_ibgp_level
    == 1                no need, just use asn
    >= 2                allocate l2_cluster as pop if not set
    == 3                allocate l3_cluster as AS if not set
    

# No need for groups, just use 
    for node in g_session:
        data = network.graph.node[node]
        print data



    print "Session:"
    pprint.pprint(g_session.nodes(data=True))
    print

    return



    edges_to_add = []
    for (s,t) in ((s,t) for s in network.graph.nodes() for t in network.graph.nodes() 
            if (s!= t # not same node
                and network.asn(s) == network.asn(t) # Only iBGP for nodes in same ASes
                )):
        s_level = network.ibgp_level(s)
        t_level = network.ibgp_level(t)
# Intra-PoP
#TODO: also make Intra-Cluster
        if (
                (network.pop(s) == network.pop(t)) # same PoP
                or (network.ibgp_cluster(s) == network.ibgp_cluster(t) != None) # same cluster and cluster is set
                ):
            if s_level == t_level == 1:
                # client to client: do nothing
                pass
            elif (s_level == 1) and (t_level == 2):
                # client -> server: up
                edges_to_add.append( (s, t, {'rr_dir': 'up'}) )
            elif (s_level == 2) and (t_level == 1):
                # server -> client: down
                edges_to_add.append( (s, t, {'rr_dir': 'down'}) )
            elif s_level == t_level == 2:
                # server -> server: over
                edges_to_add.append( (s, t, {'rr_dir': 'over'}) )
        else:
# Inter-PoP
            if s_level == t_level == 2:
                edges_to_add.append( (s, t, {'rr_dir': 'over'}) )


    # Add with placeholders for ingress/egress policy
    network.g_session.add_edges_from(edges_to_add)

    # And mark route-reflector on physical graph
    for node, data in network.graph.nodes(data=True):
        route_reflector = False
        if int(data.get("ibgp_level")) > 1:
            route_reflector = True
        network.graph.node[node]['route_reflector'] = route_reflector
    """

def initialise_ebgp(network):
    """Adds edge for links that have router in different ASes

    >>> network = ank.example_multi_as()
    >>> initialise_ebgp(network)
    >>> network.g_session.edges()
    [('2d', '3a'), ('3a', '1b'), ('1c', '2a')]
    """
    LOG.debug("Initialising eBGP")
    edges_to_add = ( (src, dst) for src, dst in network.graph.edges()
            if network.asn(src) != network.asn(dst))
    edges_to_add = list(edges_to_add)
    network.g_session.add_edges_from(edges_to_add)

def initialise_ibgp(network):
    LOG.debug("Initialising iBGP")
    configure_ibgp_rr(network)

def initialise_bgp_sessions(network):
    """ add empty ingress/egress lists to each session.
    Note: can't do in add_edges_from due to:
    http://www.ferg.org/projects/python_gotchas.html#contents_item_6
    """
    LOG.debug("Initialising iBGP sessions")
    for (u,v) in network.g_session.edges():
        network.g_session[u][v]['ingress'] = []
        network.g_session[u][v]['egress'] = []

    return

def initialise_bgp_attributes(network):
    LOG.debug("Initialising BGP attributes")
    for node in network.g_session:
        network.g_session.node[node]['tags'] = {}
        network.g_session.node[node]['prefixes'] = {}


def initialise_bgp(network):
    LOG.debug("Initialising BGP")
    if len(network.g_session):
        LOG.warn("Initialising BGP for non-empty session graph. Have you already"
                " specified a session graph?")
        #TODO: throw exception here
        return
    initialise_ebgp(network)
    initialise_ibgp(network)
    initialise_bgp_sessions(network)
    initialise_bgp_attributes(network)

def ebgp_routers(network):
    """List of all routers with an eBGP link

    >>> network = ank.example_multi_as()
    >>> initialise_ebgp(network)
    >>> ebgp_routers(network)
    ['2d', '3a', '1b', '1c', '2a']
    """
    return list(set(item for pair in ebgp_edges(network) for item in pair))

def ibgp_routers(network):
    """List of all routers with an iBGP link"""
    return list(set(item for pair in ibgp_edges(network) for item in pair))

def get_ebgp_graph(network):
    """Returns graph of eBGP routers and links between them."""
#TODO: see if just use subgraph here for efficiency
    ebgp_graph = network.g_session.subgraph(ebgp_routers(network))
    ebgp_graph.remove_edges_from( ibgp_edges(network))
    return ebgp_graph

def get_ibgp_graph(network):
    """Returns iBGP graph (full mesh currently) for an AS."""
#TODO: see if just use subgraph here for efficiency
    ibgp_graph = network.g_session.subgraph(ibgp_routers(network))
    ibgp_graph.remove_edges_from( ebgp_edges(network))
    return ibgp_graph
