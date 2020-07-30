from cachecontrol import CacheControl
from cachecontrol.caches import FileCache
from cachecontrol.heuristics import ExpiresAfter
from rdflib import Graph, URIRef, RDF, RDFS, Literal
from rdflib.namespace import Namespace
import requests

session = CacheControl(requests.Session(), cache=FileCache('.cache'), heuristic=ExpiresAfter(days=1))

unlabelled = session.post('https://staging.gss-data.org.uk/sparql',
                          headers={'Accept': 'application/sparql-results+json'},
                          data={
                              'query': '''PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?o
WHERE {
  ?s ?p ?o .
  FILTER (STRSTARTS(STR(?o), 'http://reference.data.gov.uk/id')) .
  FILTER NOT EXISTS { ?o rdfs:label ?l } .
}'''}
                          )

references = (binding['o']['value'] for binding in unlabelled.json()['results']['bindings']
              if binding['o']['type'] == 'uri')

SCOVO = Namespace('http://purl.org/NET/scovo#')
TIME = Namespace('http://www.w3.org/2006/time#')
GREGORIAN_INTERVAL = 'http://reference.data.gov.uk/id/gregorian-interval/'
GREGORIAN_INSTANT = 'http://reference.data.gov.uk/id/gregorian-instant/'

result = Graph()
for refURI in references:
    turtle = session.get(refURI, headers={'Accept': 'text/turtle'})
    if turtle.status_code != requests.codes.ok:
        print(f'Error {turtle.status_code} for <{refURI}>')
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

with open('missing-periods.ttl', 'wb') as f:
    result.serialize(f, format='text/turtle')
