"""Test module for validating Python cert setup for Kafka SSL.

.. hidden::

	Author: Chris Satterthwaite (CS)
	Contributors:
	Version info:
	  1.0 : (CS) Created Dec 28, 2019

"""

import sys
import traceback
import os
import json
import time
from contextlib import suppress
from confluent_kafka import KafkaError

thisPath = os.path.dirname(os.path.abspath(__file__))
basePath = os.path.abspath(os.path.join(thisPath, '..', 'framework'))
if basePath not in sys.path:
	sys.path.append(basePath)

import env
env.addLibPath()
import utils
logger = utils.setupLogger('TestService', env, 'logSettingsServices.json', directoryName='service')
logger.info('Starting apiKafkaTest...')


def getKafkaConsumer(globalSettings):
	"""Simple wrapper to get the parameters and connect the kafka consumer."""
	kafkaEndpoint = globalSettings['kafkaEndpoint']
	useCertsWithKafka = globalSettings['useCertificatesWithKafka']
	kafkaCaRootFile = os.path.join(env.configPath, globalSettings['kafkaCaRootFile'])
	kafkaCertFile = os.path.join(env.configPath, globalSettings['kafkaCertificateFile'])
	kafkaKeyFile = os.path.join(env.configPath, globalSettings['kafkaKeyFile'])
	kafkaTopic = globalSettings['kafkaTopic']
	## Connect the consumer
	kafkaConsumer = None
	try:
		kafkaConsumer = utils.attemptKafkaConsumerConnection(logger, kafkaEndpoint, kafkaTopic, useCertsWithKafka, kafkaCaRootFile, kafkaCertFile, kafkaKeyFile)
	except KafkaError:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('KafkaError in getKafkaConsumer: {}'.format(exception))
	except:
		exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Exception in getKafkaConsumer: {}'.format(exception))

	return kafkaConsumer


def consumerWrapper(globalSettings):
	"""Wait for kafka results, and send into the resultProcessingUtility."""
	print('Inside consumerWrapper')
	logger.debug('Inside consumerWrapper')
	kafkaErrorCount = 0
	kafkaConsumer = getKafkaConsumer(globalSettings)
	while kafkaConsumer is not None:
		try:
			message = kafkaConsumer.poll(1)
			print('consumerWrapper: after consume')
			if message is None:
				continue
			if message.error():
				logger.debug('processKafkaResults: Kafka error: {error!r}', error=message.error())
				## This might be a false positive if kafka goes down
				continue
			else:
				thisMsg = json.loads(message.value().decode('utf-8'))
				print('consumerWrapper: Data received for processing: {}'.format(thisMsg))

		except (KeyboardInterrupt, SystemExit):
			print('Interrrupt received...')
			break
		except:
			print('Exception in consumerWrapper...')
			exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
			logger.error('consumerWrapper: exception in kafka wait loop: {}'.format(str(exception)))
			kafkaErrorCount += 1
			try:
				if kafkaErrorCount < 3:
					print('consumerWrapper kafkaErrorCount {}'.format(kafkaErrorCount))
					with suppress(Exception):
						logger.error('consumerWrapper kafkaErrorCount {}'.format(kafkaErrorCount))
					time.sleep(2)
				else:
					print('consumerWrapper kafkaErrorCount {}... exiting.'.format(kafkaErrorCount))
					with suppress(Exception):
						logger.error('consumerWrapper kafkaErrorCount {}'.format(kafkaErrorCount))
			except:
				exception = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
				logger.error('Exception in consumerWrapper second catch: {}'.format(exception))
				print('Exception in consumerWrapper second catch: {}'.format(exception))

	print('Leaving consumerWrapper...')
	logger.debug('Leaving consumerWrapper...')

	## end consumerWrapper
	return


def getKafkaProducer(globalSettings):
	"""Simple wrapper to get the parameters and connect the kafka producer."""
	kafkaEndpoint = globalSettings['kafkaEndpoint']
	useCertsWithKafka = globalSettings['useCertificatesWithKafka']
	kafkaCaRootFile = os.path.join(env.configPath, globalSettings['kafkaCaRootFile'])
	kafkaCertFile = os.path.join(env.configPath, globalSettings['kafkaCertificateFile'])
	kafkaKeyFile = os.path.join(env.configPath, globalSettings['kafkaKeyFile'])
	## Connect to the producer
	kafkaProducer = utils.createKafkaProducer(logger, kafkaEndpoint, useCertsWithKafka, kafkaCaRootFile, kafkaCertFile, kafkaKeyFile)
	if kafkaProducer is None:
		raise EnvironmentError('Unable to connect a KafkaProducer.')

	## end getKafkaProducer
	return kafkaProducer


def kafkaDeliveryReport(err, msg):
	""" Called once for each message produced to indicate delivery result.
		Triggered by poll() or flush(). """
	if err is not None:
		print('Message delivery failed: {}'.format(err))
		logger.error('Message delivery failed: {}'.format(err))
	else:
		print('Message delivered to {} [{}]'.format(msg.topic(), msg.partition()))
		logger.debug('Message delivered to {} [{}]'.format(msg.topic(), msg.partition()))


def producerWrapper(globalSettings, content):
	"""Send results into Kafka as input for the resultsProcessingClient."""
	## Establish a connection
	kafkaProducer = getKafkaProducer(globalSettings)
	kafkaTopic = globalSettings['kafkaTopic']
	logger.debug('Kafka producer established')
	for x in range(3):
		## Send the message
		content['id'] = x
		logger.debug('Sending content to Kafka: {}'.format(content))
		kafkaProducer.produce(kafkaTopic, value=json.dumps(content).encode('utf-8'), callback=kafkaDeliveryReport)
		logger.debug('Polling...')
		kafkaProducer.poll(0)

	logger.debug('Flushing...')
	kafkaProducer.flush(3)
	logger.debug('Flushed kafka producer using topic {}'.format(kafkaTopic))
	kafkaProducer = None

	## end producerWrapper
	return


def printUsage():
	print('\nUsage: ')
	print('  > ', sys.argv[0], ' [producer|consumer]\n')


def main():
	try:
		globalSettings = utils.loadSettings(os.path.join(env.configPath, "globalSettings.json"))
		if len(sys.argv) < 2:
			printUsage()
		directive = sys.argv[1].lower()
		if directive == 'producer':
			content = {'objects': [{'class_name': 'URL', 'identifier': 1, 'data': {'name': 'https://cmsconstruct.com'}}], 'source': 'apiKafkaTest', 'links': []}
			producerWrapper(globalSettings, content)
		elif directive == 'consumer':
			consumerWrapper(globalSettings)
		else:
			printUsage()

	except:
		stacktrace = traceback.format_exception(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])
		logger.error('Error in apiKafkaTest utility: {}'.format(str(stacktrace).strip()))

if __name__ == '__main__':
	sys.exit(main())
