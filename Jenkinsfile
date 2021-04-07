@Library('pmd@family-pmd4') _

import uk.org.floop.jenkins_pmd.Drafter

pipeline {
    agent {
        label 'master'
    }
    stages {
        stage('Generate reference intervals') {
            agent {
                docker {
                    image 'cloudfluff/databaker'
                    reuseNode true
                }
            }
            steps {
                script {
                    def pmd = pmdConfig('pmd')
                    withEnv(["SPARQL_URL=${pmd.config.base_uri}/sparql"]) {
                        sh 'python main.py'
                    }
                }
            }
        }
        stage('Publish') {
            steps {
                script {
                    def pmd = pmdConfig('pmd')
                    for (myDraft in pmd.drafter
                            .listDraftsets(Drafter.Include.OWNED)
                            .findAll { it['display-name'] == env.JOB_NAME }) {
                        pmd.drafter.deleteDraftset(myDraft.id)
                    }
                    def id = pmd.drafter.createDraftset(env.JOB_NAME).id
                    String graph = "http://gss-data.org.uk/graph/reference-intervals"
                    echo "Adding reference intervals to ${graph}"
                    pmd.drafter.addData(id, "${WORKSPACE}/missing-intervals.ttl", "text/turtle", "UTF-8", graph)
                    pmd.drafter.publishDraftset(id)
                }
            }
        }
    }
    post {
        always {
            archiveArtifacts '*.ttl'
        }
    }
}
