"""Gradientes medios y Adam compartidos, sin transporte ni operaciones IA nuevas."""
import math
from .model import SHAPES, finite, loss_and_gradients, validate_weights, vector


def compute_gradients(weights, batch, gradient_fn=loss_and_gradients):
    if not batch:
        raise ValueError('invalid_training_batch')
    weights=validate_weights(weights)
    gradients={key:[0.0]*count for key,count in SHAPES.items()}
    loss_sum=0.0
    for pixels,label in batch:
        pixels=vector(pixels,256,normalized=True)
        if type(label) is not int or not 0<=label<3:
            raise ValueError('invalid_training_label')
        loss,local=gradient_fn(weights,pixels,label)
        loss_sum=finite(loss_sum+finite(loss))
        local=validate_weights(local)
        for key in SHAPES:
            for i,value in enumerate(local[key]):gradients[key][i]+=value/len(batch)
    return finite(loss_sum/len(batch)),validate_weights(gradients)


class Adam:
    def __init__(self,learning_rate=.003):
        if not math.isfinite(learning_rate) or learning_rate<=0:
            raise ValueError('invalid_learning_rate')
        self.learning_rate=learning_rate
        self.step=0
        self.first={key:[0.0]*count for key,count in SHAPES.items()}
        self.second={key:[0.0]*count for key,count in SHAPES.items()}

    def apply(self,weights,gradients):
        # Calculate into independent buffers; a failed update cannot leave partial state.
        weights={key:list(values) for key,values in validate_weights(weights).items()}
        gradients=validate_weights(gradients)
        norm=math.sqrt(sum(value*value for values in gradients.values() for value in values))
        if not math.isfinite(norm):raise ValueError('nonfinite_gradient_norm')
        scale=min(1.0,5.0/max(norm,1e-30));step=self.step+1
        first={k:v[:] for k,v in self.first.items()};second={k:v[:] for k,v in self.second.items()}
        for key in SHAPES:
            for i,value in enumerate(gradients[key]):
                gradient=finite(value*scale)
                first[key][i]=finite(.9*first[key][i]+.1*gradient)
                second[key][i]=finite(.999*second[key][i]+.001*gradient*gradient)
                estimate=first[key][i]/(1-.9**step)
                variance=second[key][i]/(1-.999**step)
                weights[key][i]=finite(weights[key][i]-self.learning_rate*estimate/(math.sqrt(variance)+1e-8))
        self.first,self.second,self.step=first,second,step
        return weights
