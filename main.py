#%%
from collections import defaultdict

from cachecontrol import CacheControl
from cachecontrol.caches import FileCache
from cachecontrol.heuristics import ExpiresAfter
from rdflib import Graph, URIRef, RDF, RDFS, Literal
from rdflib.namespace import Namespace
from os import environ

import requests

SPARQL_URL = environ.get('SPARQL_URL', 'http://staging.gss-data.org.uk/sparql')

# TODO: Fix this later - the staging pipeline points to the wrong endpoint,
# the environment variable needs to be set properly.

if SPARQL_URL == "http://gss-data.org.uk/sparql":
    SPARQL_URL = "http://staging.gss-data.org.uk/sparql"

print(f"Looking for missing reference periods at {SPARQL_URL}.")

response = requests.get(
        SPARQL_URL,
        allow_redirects=True,
        headers={'Accept': 'application/sparql-results+json'},
        params={'query': '''
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX qb: <http://purl.org/linked-data/cube#>
PREFIX sdmxdim: <http://purl.org/linked-data/sdmx/2009/dimension#>
PREFIX reftime: <http://reference.data.gov.uk/def/intervals/>

SELECT DISTINCT ?dsgraph ?o WHERE {
  {
    BIND (sdmxdim:refPeriod as ?d)
  } UNION {
    ?d a qb:DimensionProperty ;
         rdfs:subPropertyOf+ sdmxdim:refPeriod .
  }
  GRAPH ?dsgraph {
    [] ?d ?o
  }
  FILTER NOT EXISTS {
    GRAPH <http://gss-data.org.uk/graph/reference-intervals> {
      ?o a reftime:Interval
    }
  }
}'''})

response.raise_for_status()

undefined = defaultdict(set)

number_responses = len(response.json().get('results').get('bindings'))
print(f"{number_responses} results found.")
if number_responses == 0 :
    print(response.content)

for binding in response.json().get('results', {}).get('bindings', []):
    if binding.get('o', {}).get('type', None) != 'uri':
        print(f'Warning, value of dimension is not a resource: {binding.get("o", {}).get("value")}')
        continue
    resource = binding.get('o', {}).get('value', None)
    dsgraph = binding.get('dsgraph', {}).get('value', None)
    if resource is not None:
        undefined[resource].add(dsgraph)

SCOVO = Namespace('http://purl.org/NET/scovo#')
TIME = Namespace('http://www.w3.org/2006/time#')
GREGORIAN_INTERVAL = 'http://reference.data.gov.uk/id/gregorian-interval/'
GREGORIAN_INSTANT = 'http://reference.data.gov.uk/id/gregorian-instant/'

result = Graph()
for refURI in undefined:
    turtle = requests.get(refURI, headers={'Accept': 'text/turtle'})
    if turtle.status_code != requests.codes.ok:
        print(f'Error {turtle.status_code} for <{refURI}>')
        for dsgraph in undefined[refURI]:
            print(f' - <{dsgraph}>')
        continue
    g = Graph()
    g.parse(data=turtle.text, format='text/turtle')
    s = URIRef(refURI)
    for t in g.objects(s, RDF.type):
        if str(t).startswith('http://reference.data.gov.uk/def/'):
            result.add((s, RDF.type, t))
    for t in [URIRef('http://reference.data.gov.uk/def/intervals/Interval'), TIME.Interval]:
        result.add((s, RDF.type, URIRef(t)))
    for p in [SCOVO.min, SCOVO.max, TIME.hasBeginning, TIME.hasEnd, RDFS.comment]:
        v = g.value(s, p)
        if v is not None:
            result.add((s, p, g.value(s, p)))

    label = g.value(s, RDFS.label)

    if str(s).startswith(GREGORIAN_INTERVAL):
        start = g.value(s, TIME.hasBeginning)
        end = g.value(s, TIME.hasEnd)
        if start is not None and end is not None and \
                str(start).endswith('T00:00:00') and str(end).endswith('T00:00:00'):
            label = Literal(str(start)[len(GREGORIAN_INSTANT):-len('T00:00:00')] + '–' +
                            str(end)[len(GREGORIAN_INSTANT):-len('T00:00:00')])

    if label is not None:
        if not label[:1].isdigit():
            colon = label.find(':')
            if colon >= 0:
                result.add((s, RDFS.label, Literal(label[colon + 1:])))
            else:
                result.add((s, RDFS.label, label))
        else:
            result.add((s, RDFS.label, label))

with open('missing-intervals.ttl', 'wb') as f:
    result.serialize(f, format='text/turtle')
