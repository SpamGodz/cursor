class ProcessingEngine:
    def __init__(self, transformations):
        self.transformations = transformations

    def process(self, data):
        for transformation in self.transformations:
            data = transformation(data)
        return data
